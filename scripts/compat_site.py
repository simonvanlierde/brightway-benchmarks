#!/usr/bin/env python3
"""Put the compat workflow's last green set of each job on the site, for site_index.py's table.

Usage: compat_site.py SITE_DIR.

Asks GitHub (through `gh`) for the newest completed `compat` run on main and how each of its
jobs ended, then for each job the newest `compat-green-*` artifact from main: the set of a
job that passed. Writes each set's requirements.txt and pylock.toml to
SITE_DIR/compat/COLUMN-PYTHON-OS/ and a summary to SITE_DIR/compat/status.json. Artifacts
expire after 90 days, so a job red for longer has no last green set. Needs `actions: read`.
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
JOB = re.compile(r"(?P<column>\w+) · Python (?P<python>[\d.]+) on (?P<os>\S+)")
GREEN = "compat-green-"
FILES = ("requirements.txt", "pylock.toml")
COLUMNS = ("latest", "floors", "pre")
# The versions the table shows, as uv's requirements.txt names them.
SHOWN = ("brightway25", "bw2calc", "bw2data", "bw2io", "numpy")


def gh(*args: str) -> bytes:
    """`gh api ARGS`'s output."""
    return subprocess.run(["gh", "api", *args], check=True, capture_output=True).stdout  # noqa: S603, S607 - gh on PATH, our own API paths


def versions(requirements: str) -> dict[str, str]:
    """The SHOWN packages' versions in a requirements.txt."""
    pins = dict(line.split("==", 1) for line in requirements.splitlines() if "==" in line)
    return {name: pins[name].split()[0] for name in SHOWN if name in pins}


def own(site: Path, path: Path) -> Path:
    """PATH, if writing it stays inside SITE. The box can write site/, so it could plant a link."""
    if path.is_symlink() or not path.resolve().is_relative_to(site.resolve()):
        msg = f"{path}: a symlink or outside {site}, refusing to write it"
        raise SystemExit(msg)
    return path


def main(site: Path) -> None:
    """Write the sets and status.json under SITE_DIR/compat."""
    runs = json.loads(gh(f"repos/{REPO}/actions/workflows/compat.yml/runs?branch=main&status=completed&per_page=1"))
    if not runs["workflow_runs"]:
        print("compat_site.py: no completed compat run on main yet")
        return
    run = runs["workflow_runs"][0]
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
        last = None
        if a := green.get(cell):
            with zipfile.ZipFile(io.BytesIO(gh(f"repos/{REPO}/actions/artifacts/{a['id']}/zip"))) as z:
                own(site, out / cell).mkdir(parents=True, exist_ok=True)
                # Only these two names are read, so an entry's path never leaves out / cell.
                for name in FILES:
                    own(site, out / cell / name).write_bytes(z.read(name))
                reqs = z.read("requirements.txt").decode()
            last = {
                "date": a["created_at"][:10],
                "run": f"https://github.com/{REPO}/actions/runs/{a['workflow_run']['id']}",
                "dir": f"compat/{cell}",
                "versions": versions(reqs),
            }
        cells.append({**m.groupdict(), "today": job["conclusion"], "green": last})
    cells.sort(key=lambda c: (COLUMNS.index(c["column"]) if c["column"] in COLUMNS else 9, c["python"], c["os"]))
    out.mkdir(parents=True, exist_ok=True)
    status = {"date": run["created_at"][:10], "run": run["html_url"], "cells": cells}
    own(site, out / "status.json").write_text(json.dumps(status, indent=1) + "\n")
    print(f"{out / 'status.json'}: {len(cells)} jobs, {sum(bool(c['green']) for c in cells)} with a green set")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
