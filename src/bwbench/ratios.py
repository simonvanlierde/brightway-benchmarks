"""Interleaved ratios between environments, and the result file that holds them.

``bwbench compare`` (``bwbench.compare``) runs a case in several environments, the arms of a
comparison, in randomized multiple interleaved trials (RMIT): each round runs every arm once,
in a new random order, so drift on a shared machine lands on all arms alike. An arm's time in
a round is the median of a few calls in one fresh process. A candidate's ratio is the
geometric mean over rounds of its time over the baseline's in the same round, with a 95%
percentile bootstrap interval over rounds. Below 1 the candidate is faster. The seconds are
context only: on a shared runner they move from week to week, the ratio much less.

The file's shape is ``ratios.schema.json`` beside this module, which documents every field.
``problems(doc)`` checks a file against it and against what the schema cannot express: valid
fingerprints, one time per round, and a ratio and interval that follow from the times.
Standard library only, apart from ``jsonschema`` in ``problems``.
"""

from __future__ import annotations

import json
import math
import random
import re
import statistics
from pathlib import Path

from bwbench.fingerprint import problems as fingerprint_problems

FORMAT = "bwbench-ratios/1"
SCHEMA = Path(__file__).with_name("ratios.schema.json")
RESAMPLES = 10_000
LEVEL = 0.95
RTOL = 1e-6  # a stored ratio against the one recomputed from the stored seconds (JSON keeps 17 digits)

CONTRIBUTED = re.compile(r"(?:^|/)ratios/contributed/([a-z0-9][a-z0-9-]*)/(\d{4}-\d{2}-\d{2})\.json$")
MAX_BYTES = 256 * 1024  # the solvers comparison at 20 rounds is about 5 KiB
# Labels a machine's own name gives: a domain name, a macOS default computer name ("Ada's
# MacBook Pro"), a Windows default one (DESKTOP-4F2K9QX).
# shortcut: only these defaults; a custom host name passes, and the pull request review catches it.
HOST_LIKE = re.compile(
    r"^[\w-]+(\.[\w-]+)+$|\.(local|lan|home|internal)$|'s[ -](macbook|imac|mac)|^(desktop|laptop)-[a-z0-9]{7}$",
    re.IGNORECASE,
)
# A home folder in the file's text, where a Windows backslash is escaped as \\.
USER_FOLDER = re.compile(r"/Users/[^/\s\"]|/home/[^/\s\"]|[A-Za-z]:\\\\Users\\\\")


def interleave(arms: list[str], rounds: int, rng: random.Random) -> list[list[str]]:
    """The run order: ROUNDS rounds, each every arm once in a fresh random order."""
    return [rng.sample(arms, len(arms)) for _ in range(rounds)]


def geometric_mean_ratio(baseline: list[float], candidate: list[float]) -> float:
    """The geometric mean over rounds of candidate / baseline, paired by round."""
    if len(baseline) != len(candidate) or not baseline:
        msg = f"{len(candidate)} candidate rounds against {len(baseline)} baseline rounds"
        raise ValueError(msg)
    return math.exp(statistics.fmean(math.log(c / b) for b, c in zip(baseline, candidate, strict=True)))


def bootstrap_interval(
    baseline: list[float], candidate: list[float], seed: int, resamples: int = RESAMPLES, level: float = LEVEL
) -> tuple[float, float]:
    """A percentile bootstrap interval for ``geometric_mean_ratio``, resampling whole rounds.

    A round's pair stays together: it shares the machine's state at that moment, which is the
    point of interleaving. Each resample draws len(rounds) rounds with replacement.
    """
    logs = [math.log(c / b) for b, c in zip(baseline, candidate, strict=True)]
    if not logs:
        msg = "no rounds to resample"
        raise ValueError(msg)
    rng = random.Random(seed)  # noqa: S311 - resampling, not a secret
    n = len(logs)
    means = sorted(statistics.fmean(rng.choices(logs, k=n)) for _ in range(resamples))
    tail = (1 - level) / 2
    lo = means[math.floor(tail * (resamples - 1))]
    hi = means[math.ceil((1 - tail) * (resamples - 1))]
    return math.exp(lo), math.exp(hi)


def problems(doc: object) -> list[str]:
    """What makes DOC not a valid ratio result file; empty when it is one."""
    from jsonschema import Draft202012Validator  # noqa: PLC0415 - only the validator needs it

    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER)
    found = [f"{'/'.join(map(str, e.absolute_path)) or '(top)'}: {e.message}" for e in validator.iter_errors(doc)]
    if found or not isinstance(doc, dict):
        return found  # the checks below assume the shape
    found += [f"fingerprint: {p}" for p in fingerprint_problems(doc["fingerprint"])]
    rounds = doc["rounds"]
    for c in doc["comparisons"]:
        where, arms = f"comparisons/{c['id']}", c["arms"]
        for name, arm in arms.items():
            if arm["missing"] is not None:
                continue
            found += [f"{where}/arms/{name}/fingerprint: {p}" for p in fingerprint_problems(arm["fingerprint"])]
            if len(arm["seconds"]) != rounds:
                found.append(f"{where}/arms/{name}: {len(arm['seconds'])} times for {rounds} rounds")
        if c["baseline"] not in arms:
            found.append(f"{where}: baseline {c['baseline']!r} is not an arm")
            continue
        base = arms[c["baseline"]]
        for r in c["ratios"]:
            cand = arms.get(r["candidate"])
            if cand is None or r["candidate"] == c["baseline"]:
                found.append(f"{where}: candidate {r['candidate']!r} is not a candidate arm")
                continue
            found += _ratio_problems(f"{where}/ratios/{r['candidate']}", r, base, cand, rounds)
    return found


def _ratio_problems(where: str, r: dict, base: dict, cand: dict, rounds: int) -> list[str]:
    if r["missing"] is not None:
        return []
    if base["missing"] is not None or cand["missing"] is not None:
        return [f"{where}: a ratio from a missing arm"]
    if len(base["seconds"]) != rounds or len(cand["seconds"]) != rounds:
        return []  # reported with the arm
    want = geometric_mean_ratio(base["seconds"], cand["seconds"])
    out = []
    if not math.isclose(r["ratio"], want, rel_tol=RTOL):
        out.append(f"{where}: ratio {r['ratio']!r}, but the seconds give {want!r}")
    lo, hi = r["ci95"]
    if not lo <= r["ratio"] <= hi:
        out.append(f"{where}: ratio {r['ratio']!r} outside its interval [{lo!r}, {hi!r}]")
    return out


def slug(machine: str) -> str:
    """The folder name for a machine label: lower case, each run of other characters one dash."""
    return re.sub(r"[^a-z0-9]+", "-", machine.lower()).strip("-")


def contribution_problems(path: Path, doc: dict) -> list[str]:
    """What keeps the file at PATH, holding DOC, out of ``ratios/contributed/``; empty when it may go in.

    On top of ``problems``: the path is ``ratios/contributed/<slug of machine>/<date created>.json``,
    the tier is ``contributed`` (only an attestation proves ``hosted``), the machine label is
    not a default host name, no user folder appears, and the file is small and regular.
    """
    if path.is_symlink() or not path.is_file():
        return [f"{path.as_posix()} is not a regular file"]
    found = []
    machine, day = str(doc.get("machine", "")), str(doc.get("created", ""))[:10]
    m = CONTRIBUTED.search(path.as_posix())
    if m is None:
        found.append(
            f"goes in ratios/contributed/<machine>/<YYYY-MM-DD>.json: ratios/contributed/{slug(machine)}/{day}.json"
        )
    else:
        if m[1] != slug(machine):
            found.append(f"folder {m[1]!r}, but machine {machine!r} gives {slug(machine)!r}")
        if m[2] != day:
            found.append(f"file name {m[2]!r}, but the run was created on {day!r}")
    if doc.get("tier") != "contributed":
        found.append(f"tier is {doc.get('tier')!r}; a contributed file says 'contributed'")
    if HOST_LIKE.search(machine):
        found.append(f"machine {machine!r} looks like a host name; use a label such as the CPU model")
    if USER_FOLDER.search(path.read_text(encoding="utf-8")):
        found.append("names a user folder (/Users/..., /home/... or C:\\Users\\...); replace it with ~")
    if (size := path.stat().st_size) > MAX_BYTES:
        found.append(f"{size // 1024} KiB, more than {MAX_BYTES // 1024} KiB")
    return found
