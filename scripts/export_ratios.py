#!/usr/bin/env python3
"""Interleaved ratio files as the comparison page's data: ``export_ratios.py RATIOS CONTRIBUTED OUT``.

Reads the newest valid file per machine: RATIOS/reference/YYYY-MM-DD.json and
RATIOS/hosted/<YYYY-MM-DD>-<run id>/<OS>.json (a checkout of the ``ratios``
branch), the newest by its ``created``, and
CONTRIBUTED/<machine>/YYYY-MM-DD.json (``ratios/contributed`` on main). A file's tier comes from
its folder: a contributed file that claims another tier is skipped, as is one that
``bwbench.ratios.problems`` rejects, each with a warning. Writes OUT/ratios.json in the shape
ui/schema/ratios.schema.json gives, or nothing when there are no files.

Each candidate gets one row per machine that ran its comparison and a summary over the machines
whose 95% interval leaves out 1: a range of speed-ups when they agree, "Depends on platform"
when they do not. A range, not a pooled estimate: the machines differ on purpose. The summary is
worked out here so the viewer computes none.
"""

import argparse
import json
import sys
import tomllib
from datetime import datetime
from pathlib import Path

from output_path import output_path

from bwbench.ratios import problems

DESCRIPTIONS = Path(__file__).resolve().parents[1] / "benchmarks" / "descriptions.toml"
TIERS = ("reference", "hosted", "contributed")
OS_NAMES = {"Darwin": "macOS"}
TITLES = {
    "solvers": "Solver",
    "install-path": "Where bw2calc comes from",
    "python": "Python version",
    "bw2calc-release": "bw2calc release",
    "bw2data-release": "bw2data release",
}
ARMS = {
    "superlu": "SuperLU",
    "umfpack": "UMFPACK",
    "pypardiso": "PyPardiso",
    "pypi": "PyPI (uv)",
    "conda-forge": "conda-forge (pixi)",
}
REASON_CHARS = 200


def times(x: float) -> str:
    """X as a multiplier to three significant figures: 1.10, 2.44, 19.9."""
    return f"{x:#.3g}".rstrip(".")


def _clear(ratio: float | None, ci95: list[float] | None) -> str:
    if ratio is None or ci95 is None:
        return "missing"
    if ci95[1] < 1:
        return "faster"
    if ci95[0] > 1:
        return "slower"
    return "unclear"  # an interval that reaches 1 shows no difference at this level


def verdict(ratio: float | None, ci95: list[float] | None) -> tuple[str, str]:
    """One machine's reading of RATIO (candidate over baseline time): its direction and its words."""
    way = _clear(ratio, ci95)
    if way == "missing":
        return way, "Not measured"
    if way == "unclear":
        return way, "No clear difference"
    assert ratio is not None  # noqa: S101 - _clear said so
    return way, f"{times(1 / ratio if way == 'faster' else ratio)}x {way}"


def _count(n: int, word: str) -> str:
    return f"{n} {word}" + ("" if n == 1 else "es" if word.endswith("S") else "s")


def summary(rows: list[dict]) -> dict:
    """The range summary over ROWS (each with ratio, ci95 and os): direction and text."""
    measured = [r for r in rows if r["ratio"] is not None]
    clear = [(_clear(r["ratio"], r["ci95"]), r) for r in measured]
    clear = [(way, r) for way, r in clear if way != "unclear"]
    if not measured:
        return {"direction": "none", "text": "Not measured on any machine"}
    if not clear:
        return {"direction": "unclear", "text": f"No clear difference on {_count(len(measured), 'machine')}"}
    ways = {way for way, _ in clear}
    if len(ways) > 1:
        faster = sum(way == "faster" for way, _ in clear)
        return {
            "direction": "mixed",
            "text": f"Depends on platform: faster on {_count(faster, 'machine')}, slower on {len(clear) - faster}",
        }
    (way,) = ways
    factors = sorted(1 / r["ratio"] if way == "faster" else r["ratio"] for _, r in clear)
    span = (
        times(factors[0]) if times(factors[0]) == times(factors[-1]) else f"{times(factors[0])} to {times(factors[-1])}"
    )
    on = f"{len(clear)} of {len(measured)} machines" if len(clear) < len(measured) else _count(len(clear), "machine")
    oses = len({r["os"] for _, r in clear})
    return {"direction": way, "text": f"{span}x {way} on {on}, {_count(oses, 'OS')}"}


def _read(path: Path, tier: str) -> dict | None:
    """PATH's ratio file when it is valid and claims TIER, else None with a warning."""
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        print(f"export_ratios: skipped {path}: {error}", file=sys.stderr)
        return None
    try:
        found = problems(doc) or ([] if doc["tier"] == tier else [f"it says {doc['tier']}, its folder {tier}"])
    except Exception as error:  # noqa: BLE001 - one file must never stop the site build
        found = [f"{type(error).__name__}: {error}"]
    if found:
        print(f"export_ratios: skipped {path}: {'; '.join(found[:3])}", file=sys.stderr)
        return None
    return doc


def _newest(paths: list[Path], tier: str) -> dict | None:
    """The valid file of PATHS with the latest ``created``, whatever its folder is called."""
    docs = [d for d in (_read(p, tier) for p in paths) if d is not None]
    # created is RFC 3339 with an offset (problems() checks the format), so the parsed times compare
    return max(docs, key=lambda d: datetime.fromisoformat(d["created"])) if docs else None


def collect(ratios: Path | None, contributed: Path | None) -> list[tuple[str, str, dict]]:
    """(machine id, tier, file) for each machine's newest valid file, reference first."""
    found: list[tuple[str, str, dict | None]] = []
    if ratios and (ratios / "reference").is_dir():
        found.append(("reference", "reference", _newest(list((ratios / "reference").glob("*.json")), "reference")))
    if ratios and (ratios / "hosted").is_dir():
        files = list((ratios / "hosted").glob("*/*.json"))
        order = {"Linux": 0, "macOS": 1, "Windows": 2}
        stems = sorted({p.stem for p in files}, key=lambda s: (order.get(s, 3), s))
        found += [(f"hosted/{s}", "hosted", _newest([p for p in files if p.stem == s], "hosted")) for s in stems]
    if contributed and contributed.is_dir():
        folders = sorted(p for p in contributed.iterdir() if p.is_dir())
        found += [
            (f"contributed/{f.name}", "contributed", _newest(list(f.glob("*.json")), "contributed")) for f in folders
        ]
    return [(machine, tier, doc) for machine, tier, doc in found if doc]


def _arm(name: str, comparison: dict) -> str:
    return f"Python {name}" if comparison["id"] == "python" else ARMS.get(name, name)


def _label(comparison: dict, candidate: str, docs: list[dict]) -> str:
    """Candidate against baseline in words; a release names its versions when every machine agrees."""
    if comparison["id"].endswith("-release"):
        package = comparison["id"].removesuffix("-release")
        pairs = {tuple(c["arms"][arm]["versions"].get(package) for arm in (candidate, c["baseline"])) for c in docs}
        if len(pairs) == 1 and None not in (pair := pairs.pop()):
            return f"{package} {pair[0]} against {pair[1]}"
    return f"{_arm(candidate, comparison)} against {_arm(comparison['baseline'], comparison)}"


def reason(comparison: dict, ratio: dict) -> str | None:
    """Why RATIO has none: the missing arm's own reason, up to the installer's output.

    compare.py writes "<what bw2calc used>: <what failed>: <the tool's own output>"; the page shows
    the first two parts, and the method links the full file.
    """
    if ratio["missing"] is None:
        return None
    arms = comparison["arms"]
    text = arms[ratio["candidate"]]["missing"] or arms[comparison["baseline"]]["missing"] or ratio["missing"]
    text = ": ".join((text.splitlines() or [""])[0].split(": ")[:2]).strip()
    return text if len(text) <= REASON_CHARS else text[: REASON_CHARS - 1].rstrip() + "…"


def build(machines: list[tuple[str, str, dict]]) -> dict:
    """The page's data from each machine's (id, tier, file), comparisons in TITLES' order."""
    about = tomllib.loads(DESCRIPTIONS.read_text(encoding="utf-8"))
    out_machines = []
    groups: dict[tuple, dict] = {}  # (id, case, params, baseline) -> comparison, machines in order
    for machine, tier, doc in machines:
        fp = doc["fingerprint"]
        out_machines.append(
            {
                "id": machine,
                "name": doc["machine"],
                "tier": tier,
                "os": OS_NAMES.get(fp["os"], fp["os"]),
                "arch": fp["arch"],
                "cpu": fp.get("cpu_model"),
                "created": doc["created"],
                "run": doc["source"]["run"] if tier == "hosted" else None,
                "commit": doc["source"]["commit"],
            }
        )
        for c in doc["comparisons"]:
            key = (c["id"], c["case"], json.dumps(c["params"], sort_keys=True), c["baseline"])
            groups.setdefault(key, {"comparison": c, "runs": []})["runs"].append((machine, out_machines[-1]["os"], c))
    comparisons = []
    for (cid, case, _, baseline), group in groups.items():
        first = group["comparison"]
        candidates: dict[str, list] = {}
        for machine, os_name, c in group["runs"]:
            for r in c["ratios"]:
                way, text = verdict(r["ratio"], r["ci95"])
                candidates.setdefault(r["candidate"], []).append(
                    {
                        "machine": machine,
                        "ratio": r["ratio"],
                        "ci95": r["ci95"],
                        "verdict": way,
                        "text": text,
                        "missing": reason(c, r),
                        "seconds": r["seconds"],
                        "_os": os_name,
                        "_comparison": c,
                    }
                )
        out_candidates = []
        for name, rows in candidates.items():
            out_candidates.append(
                {
                    "name": name,
                    "label": _label(first, name, [r["_comparison"] for r in rows]),
                    "summary": summary([{**r, "os": r["_os"]} for r in rows]),
                    "rows": [{k: v for k, v in r.items() if not k.startswith("_")} for r in rows],
                }
            )
        comparisons.append(
            {
                "id": cid,
                "title": TITLES.get(cid, cid),
                "case": case,
                "case_name": about["labels"]["benchmarks"].get(case, case),
                "description": about["benchmarks"].get(case, ""),
                "params": [
                    {
                        "name": about["labels"]["params"].get(k, k),
                        "value": str(v),
                        "note": about.get("values", {}).get(k, {}).get(str(v)),
                    }
                    for k, v in first["params"].items()
                ],
                "baseline": baseline,
                "candidates": out_candidates,
            }
        )
    order: list[str] = list(TITLES)
    comparisons.sort(key=lambda c: order.index(str(c["id"])) if c["id"] in order else len(order))
    return {"format_version": 1, "machines": out_machines, "comparisons": comparisons}


def _builds(machine: tuple[str, str, dict]) -> bool:
    """Whether MACHINE's file builds on its own; one that does not is skipped, with a warning."""
    try:
        build([machine])
    except Exception as error:  # noqa: BLE001 - one file must never stop the site build
        print(f"export_ratios: skipped {machine[0]}: {type(error).__name__}: {error}", file=sys.stderr)
        return False
    return True


def export(ratios: Path | None, contributed: Path | None, out: Path) -> dict | None:
    """Write OUT/ratios.json from the newest files; None, and no file, when there are none."""
    machines = [m for m in collect(ratios, contributed) if _builds(m)]
    if not machines:
        print("export_ratios: no ratio files, so the site has no comparison page data", file=sys.stderr)
        return None
    data = build(machines)
    out.mkdir(parents=True, exist_ok=True)
    output_path(out / "ratios.json").write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return data


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("ratios", type=Path, help="a checkout of the ratios branch")
    parser.add_argument("contributed", type=Path, help="ratios/contributed on main")
    parser.add_argument("out", type=Path, help="the UI's data folder")
    args = parser.parse_args()
    export(args.ratios, args.contributed, args.out)
