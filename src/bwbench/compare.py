"""``bwbench compare``: interleaved ratios between environments on this machine, as one result file.

    bwbench compare [COMPARISON ...] -o FILE      # solvers when none is named; `all` for every one
    bwbench validate FILE ...

Each comparison times one catalogue case in two or more environments (arms). Each arm's
environment is built here under ``--work``: a uv virtual environment from PyPI, or a pixi
environment from conda-forge. Then the arms run in interleaved rounds (``bwbench.ratios``),
each call in a fresh process (``bwbench.timecase``). An arm that cannot be installed or run
here is recorded as missing, with the reason. The comparisons:

- ``solvers``: UMFPACK and PyPardiso against SuperLU in one environment, by hiding the others.
- ``install-path``: bw2calc from conda-forge (pixi) against PyPI (uv).
- ``python``: Python 3.12, 3.14 and 3.15 against 3.13.
- ``bw2calc-release``, ``bw2data-release``: the latest release against the one before, on
  macOS and Windows only (the benchmark node has the full histories on Linux).

Every arm other than the solvers' runs SuperLU, so its ratio is the install's, the
interpreter's or the release's, not a solver change. It runs from a checkout or as installed
(``uvx --from git+https://github.com/simonvanlierde/brightway-benchmarks bwbench compare``),
which carries the cases in ``bwbench/cases``. It needs ``uv``, and ``pixi`` for ``install-path``.

Exit codes: 0 written (or valid), 1 a file has problems (validate), 2 usage error, 3 could not run.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import platform
import random
import re
import shutil
import signal
import statistics
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from importlib import metadata
from pathlib import Path

from bwbench.fingerprint import fingerprint
from bwbench.ratios import (
    FORMAT,
    RESAMPLES,
    USER_FOLDER,
    bootstrap_interval,
    contribution_problems,
    geometric_mean_ratio,
    interleave,
    problems,
    ratio_seed,
    slug,
)
from bwbench.timecase import BENCHMARKS

PACKAGE = Path(__file__).resolve().parent
PROBE = PACKAGE / "fingerprint.py"
STAGE = ".bwbench-stage"  # the arms' copy of this package, in the --work folder
SOLVERS = ("pypardiso", "scikits.umfpack")  # what bw2calc picks over SuperLU when it can import it
TIMEOUT = 900  # seconds for one install or one timed process
FIRST_SCORE = ("bench_lca.SingleScore.time_first_score", {"size": "smoke", "cls": "LCA"})
WRITE = ("bench_write.DatabaseWrite.time_write", {"size": "smoke"})


@dataclass(frozen=True)
class Env:
    """An environment to build: who installs, which Python, what. ``optional`` may fail to install."""

    installer: str  # "uv" or "pixi"
    python: str
    requirements: tuple[str, ...]
    optional: tuple[str, ...] = ()


@dataclass(frozen=True)
class Arm:
    """One side of a comparison: an environment, the modules hidden in it, the solver it must use."""

    name: str
    env: Env
    hide: tuple[str, ...] = SOLVERS
    solver: str = "superlu"


@dataclass(frozen=True)
class Comparison:
    """A case timed in a baseline arm and candidate arms."""

    id: str
    case: str
    params: dict
    baseline: Arm
    candidates: tuple[Arm, ...]


@dataclass
class Built:
    """A built environment, or why it could not be built."""

    python: Path | None = None
    lock: Path | None = None
    fingerprint: dict | None = None
    failed: str | None = None
    left_out: dict[str, str] = field(default_factory=dict)  # optional requirement -> why it did not install


def comparisons(system: str, latest: dict[str, str]) -> dict[str, Comparison]:
    """Every comparison that runs on SYSTEM (``platform.system()``); LATEST maps a package to its newest release."""
    uv = Env("uv", "3.13", ("bw2calc",))
    solvers = Env("uv", "3.13", ("bw2calc",), optional=("scikit-umfpack", "pypardiso"))
    out = {
        "solvers": Comparison(
            "solvers",
            *FIRST_SCORE,
            Arm("superlu", solvers),
            (
                Arm("umfpack", solvers, hide=("pypardiso",), solver="umfpack"),
                Arm("pypardiso", solvers, hide=(), solver="pypardiso"),
            ),
        ),
        "install-path": Comparison(
            "install-path", *FIRST_SCORE, Arm("pypi", uv), (Arm("conda-forge", Env("pixi", "3.13", ("bw2calc",))),)
        ),
        "python": Comparison(
            "python",
            *FIRST_SCORE,
            Arm("3.13", uv),
            tuple(Arm(v, Env("uv", v, ("bw2calc",))) for v in ("3.12", "3.14", "3.15")),
        ),
    }
    if system in {"Darwin", "Windows"}:
        # bw2data does not depend on bw2calc, which its write case checks the score with.
        for pkg, case, extra in (("bw2calc", FIRST_SCORE, ()), ("bw2data", WRITE, ("bw2calc",))):
            if pkg not in latest:  # compare() resolves releases only when a release comparison runs
                continue
            out[f"{pkg}-release"] = Comparison(
                f"{pkg}-release",
                *case,
                Arm("previous", Env("uv", "3.13", (f"{pkg}<{latest[pkg]}", *extra))),
                (Arm("latest", Env("uv", "3.13", (f"{pkg}=={latest[pkg]}", *extra))),),
            )
    return out


def _run(args: list[str], cwd: Path, **kw: object) -> subprocess.CompletedProcess[str]:
    """ARGS' result; a process that outlives TIMEOUT is killed and fails with exit code -1."""
    try:
        return subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=TIMEOUT, check=False, **kw)  # noqa: S603  # ty: ignore[no-matching-overload]
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(args, -1, "", f"timed out after {TIMEOUT} s")


def _redact(text: str) -> str:
    r"""TEXT with the home folder and every user folder (``USER_FOLDER``) replaced by ``~``.

    Either separator and any case, so Windows short names from TEMP (``C:\Users\ADALIN~1``)
    and ``C:/Users/ada`` go too. A home of ``/`` (``docker run --user`` without a passwd entry)
    is no user's folder and stays.
    """
    home = Path.home()
    folders = [USER_FOLDER.pattern]
    if home.parent != home:
        parts = [re.escape(p) for p in re.split(r"[\\/]+", str(home).strip("\\/"))]
        lead = r"[\\/]+" if str(home)[:1] in "\\/" else ""
        folders.insert(0, lead + r"[\\/]+".join(parts) + r"(?![^\\/\s\"'])")
    return re.sub("|".join(folders), "~", text, flags=re.IGNORECASE)


def _tail(proc: subprocess.CompletedProcess[str], lines: int = 5) -> str:
    text = _redact((proc.stderr or proc.stdout).strip()).splitlines()
    return " / ".join(text[-lines:]) or f"exit {proc.returncode}"


def latest_release(package: str, work: Path) -> str:
    """The newest release of PACKAGE that uv resolves for Python 3.13 (it honours ``UV_EXCLUDE_NEWER``)."""
    proc = _run(
        ["uv", "pip", "compile", "--python-version", "3.13", "--no-header", "--no-annotate", "-"], work, input=package
    )
    for line in proc.stdout.splitlines():
        name, _, version = line.partition("==")
        if name.strip().lower() == package:
            return version.strip()
    msg = f"uv could not resolve {package}: {_tail(proc)}"
    raise RuntimeError(msg)


PIXI_PLATFORMS = {
    ("Linux", "x86_64"): "linux-64",
    ("Linux", "aarch64"): "linux-aarch64",
    ("Darwin", "arm64"): "osx-arm64",
    ("Darwin", "x86_64"): "osx-64",
    ("Windows", "AMD64"): "win-64",
}


def build(env: Env, folder: Path) -> Built:
    """Build ENV in FOLDER, record its resolved set as its lock and fingerprint it.

    FOLDER is emptied first: uv refuses to create a venv over one a former run left there.
    """
    shutil.rmtree(folder, ignore_errors=True)
    folder.mkdir(parents=True)
    built = _build_pixi(env, folder) if env.installer == "pixi" else _build_uv(env, folder)
    if built.failed is None and built.python is not None:
        proc = _run([str(built.python), "-I", str(PROBE), str(built.lock)], folder)
        with contextlib.suppress(ValueError):
            built.fingerprint = None if proc.returncode else json.loads(proc.stdout)
        if built.fingerprint is None:
            built.failed = f"fingerprint: {_tail(proc)}"
    return built


def _build_uv(env: Env, folder: Path) -> Built:
    venv = folder / "venv"
    proc = _run(["uv", "venv", "--quiet", "--python", env.python, str(venv)], folder)
    if proc.returncode:
        return Built(failed=f"uv venv --python {env.python}: {_tail(proc)}")
    py = venv / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    proc = _run(["uv", "pip", "install", "--quiet", "--python", str(py), *env.requirements], folder)
    if proc.returncode:
        return Built(failed=f"uv pip install {' '.join(env.requirements)}: {_tail(proc)}")
    lock = folder / "requirements.txt"
    built = Built(python=py, lock=lock)
    for extra in env.optional:  # one at a time, so one that cannot build here leaves the others
        proc = _run(["uv", "pip", "install", "--quiet", "--python", str(py), extra], folder)
        if proc.returncode:
            built.left_out[extra] = _tail(proc)
    proc = _run(["uv", "pip", "freeze", "--python", str(py)], folder)
    if proc.returncode or not proc.stdout.strip():  # the lock would name no environment
        return Built(failed=f"uv pip freeze: {_tail(proc)}")
    lock.write_text(proc.stdout, encoding="utf-8")
    return built


def _build_pixi(env: Env, folder: Path) -> Built:
    if shutil.which("pixi") is None:
        return Built(failed="pixi is not installed")
    plat = PIXI_PLATFORMS.get((platform.system(), platform.machine()))
    if plat is None:
        return Built(failed=f"no conda-forge platform for {platform.system()} {platform.machine()}")
    deps = "\n".join(f'{r} = "*"' for r in env.requirements)
    (folder / "pixi.toml").write_text(
        f'[workspace]\nname = "bwbench-arm"\nchannels = ["conda-forge"]\nplatforms = ["{plat}"]\n\n'
        f'[dependencies]\npython = "{env.python}.*"\n{deps}\n',
        encoding="utf-8",
    )
    manifest = ["--no-config", "--manifest-path", str(folder / "pixi.toml")]
    for step in (["pixi", "lock", *manifest], ["pixi", "install", "--frozen", *manifest]):
        proc = _run(step, folder)
        if proc.returncode:
            return Built(failed=f"{' '.join(step[:2])}: {_tail(proc)}")
    prefix = folder / ".pixi" / "envs" / "default"
    py = prefix / ("python.exe" if sys.platform == "win32" else "bin/python")
    return Built(python=py, lock=folder / "pixi.lock")


def stage(work: Path) -> Path:
    """Copy this package, with the cases in ``bwbench/cases``, to WORK/.bwbench-stage: the arms' import path.

    Only this package: the folder it is installed in also holds the packages of the environment
    bwbench runs in (uvx's NumPy, say), which would shadow the arm's own. The folder name is one
    no checkout has, so ``--work .`` in a checkout leaves its ``src/bwbench`` alone.
    """
    dest = work.resolve() / STAGE / "bwbench"
    if PACKAGE.is_relative_to(dest) or dest.is_relative_to(PACKAGE):
        msg = f"cannot stage into {dest.as_posix()!r}: bwbench runs from inside it"
        raise RuntimeError(msg)
    skip = shutil.ignore_patterns("__pycache__")
    shutil.rmtree(dest, ignore_errors=True)
    shutil.copytree(PACKAGE, dest, ignore=skip)
    if not (dest / "cases").is_dir():  # a checkout: the cases sit beside src/
        shutil.copytree(BENCHMARKS, dest / "cases", ignore=skip)
    return dest.parent


def time_arm(arm: Arm, built: Built, case: str, params: dict, repeats: int, work: Path) -> dict:
    """One fresh process of ARM timing CASE: the worker's JSON object, or ``{"missing": why}``."""
    src = work / STAGE  # from stage()
    env = os.environ | {
        "PYTHONPATH": os.pathsep.join([str(src), str(src / "bwbench" / "cases")]),
        "BWBENCH_HIDE": ",".join(arm.hide),
        "PYTHONUTF8": "1",
    }
    args = [str(built.python), "-m", "bwbench.timecase", case, json.dumps(params), str(repeats)]
    proc = _run(args, work, env=env)
    if proc.returncode:
        return {"missing": f"the case failed: {_tail(proc)}"}
    lines = proc.stdout.strip().splitlines()
    out = None
    with contextlib.suppress(ValueError):
        out = json.loads(lines[-1]) if lines else None
    if not isinstance(out, dict) or not {"seconds", "solver", "versions", "missing"} <= out.keys():
        return {"missing": f"the case printed no JSON object: {_tail(proc)}"}
    if out["missing"] is None and out["solver"] is None:
        # Ratios between runs that never reached bw2calc's solver would compare nothing.
        out["missing"] = "bw2calc's solver is unknown: the case never imported bw2calc, or this release does not say"
    elif out["missing"] is None and out["solver"] != arm.solver:
        wanted = "scikit-umfpack" if arm.solver == "umfpack" else arm.solver
        why = built.left_out.get(wanted, "")
        out["missing"] = f"bw2calc used {out['solver']}, not {arm.solver}" + (
            f": {wanted} did not install: {why}" if why else ""
        )
    return out


def measure(c: Comparison, built: dict[Env, Built], rounds: int, repeats: int, seed: int, work: Path) -> dict:
    """Run C's arms in interleaved rounds; the comparison's entry in the result file.

    SEED is the file's: the run order and each ratio's bootstrap seed follow from it and C's id.
    """
    arms = (c.baseline, *c.candidates)
    rng = random.Random(f"{seed}/{c.id}")  # noqa: S311 - the run order, not a secret
    entry: dict[str, dict] = {
        a.name: {
            "installer": a.env.installer,
            "python": a.env.python,
            "requirements": list(a.env.requirements + a.env.optional),
            "solver": None,
            "versions": {},
            "fingerprint": built[a.env].fingerprint,
            "seconds": [],
            "missing": built[a.env].failed,
        }
        for a in arms
    }
    for i, order in enumerate(interleave([a.name for a in arms], rounds, rng), 1):
        for name in order:
            arm, e = next(a for a in arms if a.name == name), entry[name]
            if e["missing"] is not None:
                continue
            out = time_arm(arm, built[arm.env], c.case, c.params, repeats, work)
            if out["missing"] is not None:
                e |= {"missing": out["missing"], "seconds": [], "solver": None, "versions": {}}
                continue
            e |= {"solver": out["solver"], "versions": out["versions"]}
            e["seconds"].append(statistics.median(out["seconds"]))
        print(f"compare: {c.id}: round {i} of {rounds}", file=sys.stderr)
    return {
        "id": c.id,
        "case": c.case,
        "params": c.params,
        "baseline": c.baseline.name,
        "arms": entry,
        "ratios": [
            ratio(entry[c.baseline.name], entry[a.name], a.name, ratio_seed(seed, c.id, a.name)) for a in c.candidates
        ],
    }


def ratio(base: dict, cand: dict, name: str, seed: int) -> dict:
    """A candidate's ratio entry: the ratio, its interval and median seconds, or why there is none."""
    for side, arm in (("baseline", base), ("candidate", cand)):
        if arm["missing"] is not None:
            return {"candidate": name, "ratio": None, "ci95": None, "seconds": None, "missing": f"{side} missing"}
    b, c = base["seconds"], cand["seconds"]
    return {
        "candidate": name,
        "ratio": geometric_mean_ratio(b, c),
        "ci95": list(bootstrap_interval(b, c, seed)),
        "seconds": {"baseline": statistics.median(b), "candidate": statistics.median(c)},
        "missing": None,
    }


def compare(ids: list[str], out: Path, rounds: int, repeats: int, tier: str, machine: str | None, work: Path) -> dict:
    """Build the arms of the comparisons IDS, measure them and write the result file to OUT."""
    work.mkdir(parents=True, exist_ok=True)
    stage(work)
    created = datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
    system = platform.system()
    wants_release = {"all", "bw2calc-release", "bw2data-release"} & set(ids) and system in {"Darwin", "Windows"}
    latest = {p: latest_release(p, work) for p in ("bw2calc", "bw2data")} if wants_release else {}
    available = comparisons(system, latest)
    chosen = list(available.values()) if "all" in ids else [available[i] for i in ids]
    built: dict[Env, Built] = {}
    for c in chosen:
        for a in (c.baseline, *c.candidates):
            if a.env not in built:
                print(
                    f"compare: building {a.env.installer} Python {a.env.python} {a.env.requirements}", file=sys.stderr
                )
                built[a.env] = build(a.env, work / f"env{len(built)}")
    seed = random.SystemRandom().randrange(2**32)
    head = os.environ.get("GITHUB_SHA") or os.environ.get("BWBENCH_COMMIT") or _commit()  # box.sh sets BWBENCH_COMMIT
    run = None
    if os.environ.get("GITHUB_RUN_ID"):
        env = os.environ
        run = f"{env['GITHUB_SERVER_URL']}/{env['GITHUB_REPOSITORY']}/actions/runs/{env['GITHUB_RUN_ID']}"
    fp = fingerprint()
    doc = {
        "format": FORMAT,
        "tier": tier,
        "machine": machine or fp["cpu_model"] or f"{fp['os']} {fp['arch']}",
        "created": created,
        "source": {"commit": head, "run": run},
        "rounds": rounds,
        "repeats": repeats,
        "seed": seed,
        "resamples": RESAMPLES,
        "fingerprint": fp,
        "comparisons": [measure(c, built, rounds, repeats, seed, work) for c in chosen],
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
    return doc


def _commit() -> str | None:
    """This repository's commit: uv's record of a git install (``uvx --from git+...``), else the checkout's HEAD."""
    with contextlib.suppress(metadata.PackageNotFoundError, TypeError, KeyError, ValueError):
        record = metadata.distribution("brightway-benchmarks").read_text("direct_url.json")
        return json.loads(record)["vcs_info"]["commit_id"]  # ty: ignore[invalid-argument-type]
    git = shutil.which("git")
    if git is None:
        return None
    proc = _run([git, "rev-parse", "HEAD"], PACKAGE)
    return proc.stdout.strip() if proc.returncode == 0 else None


def validate(files: list[Path], *, contribution: bool = False) -> int:
    """1 if any of FILES is not a valid result file (with CONTRIBUTION: contribution), each problem on stderr."""
    bad = 0
    for path in files:
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
            found = problems(doc)
            if contribution:
                found += contribution_problems(path, doc if isinstance(doc, dict) else {})
        except (OSError, ValueError) as e:
            found = [f"cannot read: {e}"]
        for p in found:
            print(f"{path.as_posix()}: {p}", file=sys.stderr)
        bad += bool(found)
    return 1 if bad else 0


def parser() -> argparse.ArgumentParser:
    """The command line."""
    p = argparse.ArgumentParser(prog="bwbench", description="Interleaved ratios between Brightway environments.")
    sub = p.add_subparsers(dest="command", required=True)
    ids = ["all", "solvers", "install-path", "python", "bw2calc-release", "bw2data-release"]
    c = sub.add_parser(
        "compare",
        help="measure ratios on this machine",
        description=__doc__.split("\n\n")[2],
        epilog="example: bwbench compare solvers install-path -o ratios.json",
    )
    c.add_argument(
        "ids",
        nargs="*",
        choices=ids,
        metavar="COMPARISON",
        help=f"one or more of {', '.join(ids)} (default: solvers)",
    )
    c.add_argument("-o", "--output", type=Path, required=True, help="the result file to write")
    c.add_argument("--rounds", type=int, default=20, help="interleaved rounds (default: 20)")
    c.add_argument("--repeats", type=int, default=3, help="timed calls per arm and round (default: 3)")
    c.add_argument("--tier", choices=["reference", "hosted", "contributed"], default="contributed")
    c.add_argument("--machine", help="a label for this machine (default: its CPU model); never a host name")
    c.add_argument(
        "--work",
        type=Path,
        help="where the environments go, each arm's folder emptied first (default: a temporary folder, removed)",
    )
    v = sub.add_parser(
        "validate",
        help="check result files",
        epilog="example: bwbench validate --contribution ratios/contributed/apple-m3-pro/2026-11-14.json",
    )
    v.add_argument("files", nargs="+", type=Path)
    v.add_argument(
        "--contribution",
        action="store_true",
        help="also check what a file in ratios/contributed/ needs: its path, tier 'contributed', no host or user names",
    )
    return p


def parse(argv: list[str] | None) -> argparse.Namespace:
    """ARGV parsed, with the solvers when no comparison is named."""
    args = parser().parse_args(argv)
    if args.command == "compare":
        args.ids = args.ids or ["solvers"]
    return args


def main(argv: list[str] | None = None) -> int:
    """Run ``bwbench`` with ARGV; the exit code."""
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", newline="\n")  # ty: ignore[unresolved-attribute]
    args = parse(argv)
    if args.command == "validate":
        return validate(args.files, contribution=args.contribution)
    if args.rounds < 2 or args.repeats < 1:
        parser().error("--rounds must be at least 2 and --repeats at least 1")
    if {"bw2calc-release", "bw2data-release"} & set(args.ids) and platform.system() not in {"Darwin", "Windows"}:
        parser().error("the release comparisons run on macOS and Windows only")
    if args.machine is not None and not 0 < len(args.machine) <= 100:
        parser().error("--machine must be 1 to 100 characters")
    if args.machine is not None and not slug(args.machine):
        parser().error(f"--machine {args.machine!r} needs ASCII letters or digits: its folder name keeps only those")
    try:
        if args.work is None:
            with tempfile.TemporaryDirectory(prefix="bwbench-compare-") as tmp:
                compare(args.ids, args.output, args.rounds, args.repeats, args.tier, args.machine, Path(tmp))
        else:
            compare(args.ids, args.output, args.rounds, args.repeats, args.tier, args.machine, args.work.resolve())
    except KeyboardInterrupt:
        print("bwbench: interrupted", file=sys.stderr)
        signal.signal(signal.SIGINT, signal.SIG_DFL)
        os.kill(os.getpid(), signal.SIGINT)
        return 130
    except (OSError, RuntimeError, subprocess.SubprocessError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 3
    print(args.output.as_posix())
    return 0


if __name__ == "__main__":
    sys.exit(main())
