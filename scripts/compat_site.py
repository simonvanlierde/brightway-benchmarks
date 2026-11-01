#!/usr/bin/env python3
"""Keep the compat workflow's green sets in the compat archive, and say how each job ended.

Usage: compat_site.py ARCHIVE_DIR.

Asks GitHub (through `gh`) for a `compat` run on main (COMPAT_RUN_ID, or else the newest
completed one) and how each of its jobs ended, then for each job the newest `compat-green-*`
artifact from main: the set of a job that passed. A set that differs from the job's newest
dated set goes to ARCHIVE_DIR/compat/COLUMN-PYTHON-OS/DATE/, with set.json for its date and run,
so a command that names that folder always installs the same set. The newest dated set is also
copied to ARCHIVE_DIR/compat/COLUMN-PYTHON-OS/, the address that follows the latest set, and a
summary goes to ARCHIVE_DIR/compat/status.json. ARCHIVE_DIR is a checkout of the `compat`
branch, so a set outlives its artifact's 90 days. Needs `actions: read`.
"""

import io
import json
import os
import re
import subprocess
import sys
import zipfile
from pathlib import Path

REPO = os.environ.get("GITHUB_REPOSITORY", "simonvanlierde/brightway-benchmarks")
# compat.yml's job name and green artifact name; tests/test_compat_site.py checks both there.
JOB = re.compile(r"(?P<column>[\w-]+) · Python (?P<python>[\d.]+) on (?P<os>\S+)")
GREEN = "compat-green-"
# The files a set may hold: pylock.toml from PyPI; environment.yml, pixi.toml and pixi.lock from
# conda-forge.
FILES = ("requirements.txt", "pylock.toml", "environment.yml", "pixi.toml", "pixi.lock")
COLUMNS = ("latest", "floors", "pre", "conda-forge", "suites")
# The versions the site shows: the packages the install line names, and what they rest on.
SHOWN = ("brightway25", "bw2calc", "bw2data", "bw2io", "bw_graph_tools", "bw_timex", "numpy")


def norm(name: str) -> str:
    """NAME as PEP 503 compares it: uv writes bw-graph-tools where pip users type bw_graph_tools."""
    return re.sub(r"[-_.]+", "-", name).lower()


def gh(*args: str) -> bytes:
    """`gh api ARGS`'s output."""
    return subprocess.run(["gh", "api", *args], check=True, capture_output=True).stdout  # noqa: S603, S607 - gh on PATH, our own API paths


def versions(requirements: str) -> dict[str, str]:
    """The SHOWN packages' versions in a requirements.txt."""
    pairs = (line.split("==", 1) for line in requirements.splitlines() if "==" in line)
    pins = {norm(name): pin for name, pin in pairs}
    return {name: pins[norm(name)].split()[0] for name in SHOWN if norm(name) in pins}


def own(site: Path, path: Path) -> Path:
    """PATH, if writing it stays inside SITE. The box can write site/, so it could plant a link."""
    if path.is_symlink() or not path.resolve().is_relative_to(site.resolve()):
        msg = f"{path}: a symlink or outside {site}, refusing to write it"
        raise SystemExit(msg)
    return path


def newest(cell: Path) -> Path | None:
    """CELL's newest dated set, if it has one: 2026-11-01.2 is the day's second set."""
    dated = [d for d in cell.glob("????-??-??*") if d.is_dir()] if cell.is_dir() else []
    return max(dated, key=lambda d: (d.name[:10], int(d.name[11:] or 1)), default=None)


def keep(site: Path, cell: Path, files: dict[str, bytes], date: str, run: str) -> Path:
    """The dated folder that holds FILES: CELL's newest one when it holds the same, or a new one.

    A dated folder is never written twice, so a command that names one installs the same set.
    """
    prev = newest(cell)
    same = prev and {n for n in FILES if (prev / n).exists()} == set(files)
    if prev and same and all((prev / n).read_bytes() == data for n, data in files.items()):
        return prev
    n = 1
    while (cell / (date if n == 1 else f"{date}.{n}")).exists():
        n += 1
    dated = own(site, cell / (date if n == 1 else f"{date}.{n}"))
    dated.mkdir(parents=True)
    for name, data in files.items():
        own(site, dated / name).write_bytes(data)
    own(site, dated / "set.json").write_text(json.dumps({"date": date, "run": run}) + "\n")
    return dated


def follow(site: Path, here: Path, dated: Path, passed: str, run: str | None = None) -> dict:
    """Copy DATED's set to HERE, the folder that follows the newest set, and describe it.

    RUN is the newest run that passed with it; without one, the run that first wrote it.
    """
    names = [name for name in FILES if (dated / name).exists()]
    for name in FILES:
        target = own(site, here / name)
        if name in names:
            target.write_bytes((dated / name).read_bytes())
        else:
            target.unlink(missing_ok=True)
    run = run or json.loads((dated / "set.json").read_text())["run"]
    own(site, here / "set.json").write_text(json.dumps({"date": passed, "run": run}) + "\n")
    return {
        "date": passed,
        "run": run,
        "dir": f"compat/{here.name}/{dated.name}",
        "latest": f"compat/{here.name}",
        "files": names,
        "versions": versions((dated / "requirements.txt").read_text()),
    }


def compat_run() -> dict | None:
    """The run COMPAT_RUN_ID names, or else the newest completed one on main."""
    if run_id := os.environ.get("COMPAT_RUN_ID"):
        return json.loads(gh(f"repos/{REPO}/actions/runs/{run_id}"))
    runs = json.loads(gh(f"repos/{REPO}/actions/workflows/compat.yml/runs?branch=main&status=completed&per_page=1"))
    return runs["workflow_runs"][0] if runs["workflow_runs"] else None


def main(site: Path) -> None:
    """Archive the green sets and write status.json under ARCHIVE_DIR/compat."""
    if not (run := compat_run()):
        print("compat_site.py: no completed compat run on main yet")
        return
    jobs = json.loads(gh(f"repos/{REPO}/actions/runs/{run['id']}/jobs?per_page=100"))["jobs"]
    # Newest first, so the first artifact of each name is its newest.
    lines = gh("--paginate", f"repos/{REPO}/actions/artifacts?per_page=100", "--jq", ".artifacts[] | @json")
    green: dict[str, dict] = {}
    for a in map(json.loads, lines.splitlines()):
        if a["name"].startswith(GREEN) and a["workflow_run"]["head_branch"] == "main" and not a["expired"]:
            green.setdefault(a["name"].removeprefix(GREEN), a)
    out = own(site, site / "compat")
    cells = []
    for job in jobs:
        m = JOB.fullmatch(job["name"])
        if not m:
            continue
        cell = "-".join(m.groups())
        here = own(site, out / cell)
        dated = run_url = None
        if a := green.get(cell):
            with zipfile.ZipFile(io.BytesIO(gh(f"repos/{REPO}/actions/artifacts/{a['id']}/zip"))) as z:
                # Only FILES are read, so an entry's path never leaves the cell's folder.
                files = {name: z.read(name) for name in FILES if name in z.namelist()}
            passed = a["created_at"][:10]
            run_url = f"https://github.com/{REPO}/actions/runs/{a['workflow_run']['id']}"
            dated = keep(site, here, files, passed, run_url)
        elif dated := newest(here):  # the artifact expired; the archive still has the set
            metadata = own(site, here / "set.json")
            saved = json.loads((metadata if metadata.is_file() else dated / "set.json").read_text())
            passed, run_url = saved["date"], saved["run"]
        last = follow(site, here, dated, passed, run_url) if dated else None
        cells.append({**m.groupdict(), "today": job["conclusion"], "green": last})
    cells.sort(key=lambda c: (COLUMNS.index(c["column"]) if c["column"] in COLUMNS else 9, c["python"], c["os"]))
    out.mkdir(parents=True, exist_ok=True)
    status = {"date": run["created_at"][:10], "run": run["html_url"], "cells": cells}
    own(site, out / "status.json").write_text(json.dumps(status, indent=1) + "\n")
    print(f"{out / 'status.json'}: {len(cells)} jobs, {sum(bool(c['green']) for c in cells)} with a green set")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
