#!/usr/bin/env python3
"""Export setup and solver evidence beside index.json, without fetching external data.

Usage: export_guidance.py COMPAT_STATUS UI_DATA_DIR [--public-base SITE_URL].
"""

import argparse
import json
import math
import sys
from pathlib import Path, PurePosixPath
from urllib.parse import urlencode, urljoin, urlsplit

from compat_site import FILES
from output_path import output_path

PUBLIC_BASE = "https://simonvanlierde.com/brightway-benchmarks/"
PLATFORMS = {
    "ubuntu-latest": ("linux", "Linux"),
    "macos-latest": ("macos", "macOS"),
    "windows-latest": ("windows", "Windows"),
}
# The benchmark machines are Linux x86-64 boxes (docs/running.md); results do not record an OS.
MEASURED_ON = "linux"
LABELS = {
    "latest": "Latest releases",
    "floors": "Dependency floors",
    "pre": "Pre-releases",
    "conda-forge": "conda-forge",
    "suites": "Upstream test suites",
}

DESCRIPTIONS = {
    "latest": "Install the latest stable releases from PyPI and run each benchmark case once on a small database.",
    "floors": (
        "Keep Brightway at its latest releases, use the lowest allowed versions of its direct dependencies, "
        "and run the small-database calculations."
    ),
    "pre": "Allow pre-release packages from PyPI and run each benchmark case once on a small database.",
    "conda-forge": (
        "Install the available Brightway packages from conda-forge and run the small-database calculations."
    ),
    "suites": (
        "Run upstream package test suites against the latest installed releases; "
        "this is broader than the small-database calculation checks."
    ),
}


def web_url(value: str) -> str:
    """A public link must name an HTTP(S) host, never an executable URL."""
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        msg = f"Not an HTTP(S) URL: {value}"
        raise ValueError(msg)
    return value


# What every install command names; the constraints file pins the rest of the tested set.
PACKAGES = "brightway25 bw_graph_tools bw_timex"


def _installs(column: str, files: list[str], folder: str) -> list[dict]:
    """One command per package manager for the set in FOLDER (a URL ending in /), read from there."""
    if column == "conda-forge":
        out = []
        if "environment.yml" in files:
            # update, not create: it makes the environment when missing, so a rerun is harmless. Its
            # own name, because --prune removes whatever else an environment holds.
            out.append(("conda", f"conda env update -n brightway-tested -f {folder}environment.yml --prune"))
        if {"pixi.toml", "pixi.lock"} <= set(files):
            out.append(("pixi", f"curl -fL -O {folder}pixi.toml -O {folder}pixi.lock && pixi install --frozen"))
        return [{"manager": m, "command": c} for m, c in out]
    if "requirements.txt" not in files:
        return []
    return [
        {"manager": "uv", "command": f"uv add {PACKAGES} -c {folder}requirements.txt"},
        {"manager": "pip", "command": f"pip install {PACKAGES} -c {folder}requirements.txt"},
    ]


def _folder(public_base: str, directory: str) -> str:
    path = PurePosixPath(directory)
    if path.is_absolute() or ".." in path.parts or path.parts[:1] != ("compat",):
        msg = "Compatibility files must stay under compat/"
        raise ValueError(msg)
    return urljoin(public_base, f"{path}/")


def _passing_set(green: dict, column: str, public_base: str) -> dict:
    dated = _folder(public_base, green["dir"])
    # A set from the compat archive has a dated folder and an undated one that follows the newest set.
    latest = _folder(public_base, green["latest"]) if green.get("latest", green["dir"]) != green["dir"] else None
    files = [name for name in FILES if name in green["files"]]
    if column == "conda-forge":
        files.sort(key=lambda name: name == "requirements.txt")  # stable: the conda files, then the rest
    out = {
        "date": green["date"],
        "run": web_url(green["run"]),
        "packages": [{"name": name, "version": version} for name, version in green["versions"].items()],
        "files": [
            {"label": name, "url": dated + name} | ({"latest": latest + name} if latest else {}) for name in files
        ],
        "installs": _installs(column, files, dated),
    }
    if latest:
        out["pinned"] = PurePosixPath(green["dir"]).name[:10]  # 2026-11-01.2 is that day's second set
        for install, follow in zip(out["installs"], _installs(column, files, latest), strict=True):
            install["latest"] = follow["command"]
    return out


def _solver_cases(index: dict, groups: dict) -> dict:
    """Index the supported first-score comparisons once, outside the report loop."""
    benches = {b["id"]: b for b in index["benchmarks"] if b["name"] == "bench_lca.SingleScore.time_first_score"}
    envs = {e["id"]: e for e in index["environments"]}
    selected = {}
    for case in index["cases"]:
        bench = benches.get(case["benchmark"])
        if not bench or case["params"] != ["'ecoinvent'", "'LCA'"]:
            continue
        env = envs[case["environment"]]
        group, label = groups.get(bench["group"]), env.get("label")
        name = {("bw2calc", "PyPardiso"): "PyPardiso", ("bw2calc", "SuperLU"): "SuperLU"}.get((group, label))
        if group == "bw2calc-conda" and label == "UMFPACK" and "mkl" not in env.get("name", "").lower():
            name = "UMFPACK · conda-forge"
        if name:
            selected.setdefault(bench["group"], []).append((case, bench, name))
    return selected


def _read_report(data_dir: Path, name: str) -> dict | None:
    """Read an optional report without following references outside its data directory."""
    relative = PurePosixPath(name)
    path = data_dir / relative
    if (
        relative.is_absolute()
        or ".." in relative.parts
        or path.is_symlink()
        or not path.resolve().is_relative_to(data_dir.resolve())
    ):
        msg = "Benchmark report must stay inside the data directory"
        raise ValueError(msg)
    return json.loads(path.read_text()) if path.is_file() else None


def solver_comparison(data_dir: Path) -> dict | None:
    """Compare three installed solver paths only when the release and machine match."""
    path = data_dir / "index.json"
    if not path.is_file():
        return None
    index = json.loads(path.read_text())
    groups = {g["id"]: g["name"] for g in index["groups"]}
    candidates = _solver_cases(index, groups)
    commits = {(c["group"], c["id"]): c for c in index["commits"] if c.get("release")}
    latest = max((c["date"] for c in commits.values() if groups.get(c["group"]) == "bw2calc"), default=None)
    releases = {c["release"] for c in commits.values() if c["date"] == latest and groups.get(c["group"]) == "bw2calc"}
    selected: dict[tuple[str, str], dict[str, dict]] = {}
    for report in index["reports"]:
        commit = commits.get((report["group"], report["commit"]))
        if not commit or commit["release"] not in releases:
            continue
        metrics = _read_report(data_dir, report["path"])
        if metrics is None:
            continue
        rows = selected.setdefault((report["machine"], commit["release"]), {})
        for case, bench, name in candidates.get(report["group"], []):
            value = metrics.get(case["id"], {}).get("latency", {}).get("value")
            if not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
                continue
            query = urlencode({"bench": bench["id"], "measure": "latency", "machine": report["machine"]})
            query += "&" + urlencode([("p", "ecoinvent"), ("p", "LCA")])
            rows[name] = {"label": name, "value": value, "unit": "ns", "href": f"?{query}"}
    for (machine, release), rows in sorted(selected.items()):
        if len(rows) == 3:
            machine_name = next((m["name"] for m in index["machines"] if m["id"] == machine), machine)
            return {
                "title": "Solver alternatives, measured on one Linux machine",
                "context": f"First LCA score · bw2calc {release} · synthetic ecoinvent-sized database · {machine_name}",
                "platform": MEASURED_ON,
                "note": (
                    "These fixed benchmark environments differ from the compatibility snapshot. "
                    "Timings do not predict every workflow or machine."
                ),
                "rows": [rows[name] for name in ("UMFPACK · conda-forge", "PyPardiso", "SuperLU")],
            }
    return None


def export(status_path: Path, data_dir: Path, public_base: str = PUBLIC_BASE) -> dict | None:
    """Write guidance.json using the supplied snapshot and already exported benchmark reports."""
    public_base = web_url(public_base).rstrip("/") + "/"
    target = data_dir / "guidance.json"
    output_path(target)
    if not status_path.is_file():
        print(f"{status_path} not found (run `just site` first): no setup guidance", file=sys.stderr)
        output_path(target).unlink(missing_ok=True)
        return None
    status = json.loads(status_path.read_text())
    out = {
        "format_version": 2,
        "title": "A tested Brightway setup",
        "intro": "Pick your platform below for a set that passed.",
        "snapshot": {"date": status["date"], "run": web_url(status["run"])},
        "platforms": [],
        "checks": [],
    }
    platforms = {}
    for cell in status["cells"]:
        os_name = cell["os"]
        if os_name not in PLATFORMS:
            continue
        platform, label = PLATFORMS[os_name]
        entry = platforms.setdefault(platform, {"id": platform, "label": label})
        column = cell["column"]
        check = {
            "id": f"{column}-{cell['python']}-{os_name}",
            "platform": platform,
            "python": cell["python"],
            "label": LABELS.get(column, column),
            **({"description": DESCRIPTIONS[column]} if column in DESCRIPTIONS else {}),
            "kind": "suites" if column == "suites" else "smoke" if column == "latest" else "diagnostic",
            "status": cell["today"] or "unknown",
            "coverage": "Package test suites" if column == "suites" else "Small-database calculation checks",
            "caveats": [],
            "run": web_url(status["run"]),
        }
        if os_name == "macos-latest" and column != "suites":
            check["caveats"].append(
                "Fast-solver cases are skipped on this macOS runner; this is not a validation of every solver."
            )
        if column == "conda-forge":
            check["caveats"].append(
                "bw_graph_tools and bw_timex are omitted because this conda-forge set does not provide them."
            )
        if green := cell.get("green"):
            check["lastPassed"] = _passing_set(green, column, public_base)
            if column == "latest" and cell["python"] == "3.13" and check["lastPassed"]["installs"]:
                entry["defaultCheck"] = check["id"]
        out["checks"].append(check)
    out["platforms"] = [platforms[key] for key in ("linux", "macos", "windows") if key in platforms]
    if comparison := solver_comparison(data_dir):
        out["solverComparison"] = comparison
    data_dir.mkdir(parents=True, exist_ok=True)
    output_path(target).write_text(json.dumps(out, indent=2) + "\n")
    return out


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("status", type=Path)
    parser.add_argument("data", type=Path)
    parser.add_argument("--public-base", default=PUBLIC_BASE)
    args = parser.parse_args()
    export(args.status, args.data, args.public_base)
