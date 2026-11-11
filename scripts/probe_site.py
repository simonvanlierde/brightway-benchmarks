#!/usr/bin/env python3
"""Collect the newest python-probe result of each Python and OS, for the site.

Usage: probe_site.py OUT_JSON.

The python-probe workflow uploads one `python-probe-PYTHON-OS` artifact per job (scripts/py_probe.py's
probe.json). The end-of-life Pythons run only on Mondays, so no single run holds every cell: this takes
each name's newest artifact from main's own python-probe runs, as compat_site.py does for the green sets,
and writes them to OUT_JSON. scripts/export_guidance.py reads that file. Needs `actions: read`.

The site must still deploy without the table, so a failure here is a `::warning::` and exit 0 with no
file written; a result too old for its cadence is left out, and shows as not checked.
"""

import io
import json
import re
import sys
import zipfile
from datetime import UTC, date, datetime
from pathlib import Path

from compat_site import REPO, GreenArtifacts, gh
from export_guidance import END_OF_LIFE

PREFIX = "python-probe-"
NAME = re.compile(r"python-probe-(?P<python>\d+\.\d+)-(?P<os>[\w-]+)")
# Enough of a step's error to name its cause; a uv build log runs to kilobytes.
ERROR = 500
# A result older than this many days is no longer a current result: a daily job (3.11 to 3.15) that has
# not produced one in 3 days has stopped, and the Monday-only end-of-life jobs get a week and two days.
MAX_AGE_DAYS = {"daily": 3, "weekly": 9}


def trim(probe: dict) -> list[dict]:
    """PROBE's steps, each error cut to ERROR characters; a step without `step` and `ok` is a KeyError."""
    return [
        {"step": s["step"], "ok": s["ok"], **{k: s[k] for k in ("declared",) if k in s}}
        | ({"error": str(s["error"])[:ERROR]} if "error" in s else {})
        for s in probe["steps"]
    ]


def stale(python: str, created: str, today: date) -> bool:
    """Whether a result made on CREATED (YYYY-MM-DD) is too old for PYTHON's cadence."""
    limit = MAX_AGE_DAYS["weekly" if python in END_OF_LIFE else "daily"]
    return (today - date.fromisoformat(created)).days > limit


def collect(today: date) -> list[dict]:
    """The newest trusted, current, well-formed result of every cell."""
    # Newest first, so the first artifact of each name is its newest.
    lines = gh("--paginate", f"repos/{REPO}/actions/artifacts?per_page=100", "--jq", ".artifacts[] | @json")
    trusted = GreenArtifacts("python-probe.yml")
    newest: dict[str, dict] = {}
    for a in map(json.loads, lines.splitlines()):
        if a["name"].startswith(PREFIX) and NAME.fullmatch(a["name"]) and a["name"] not in newest and trusted(a):
            newest[a["name"]] = a
    cells = []
    for name, a in newest.items():
        python = NAME.fullmatch(name)["python"]
        if stale(python, a["created_at"][:10], today):
            print(f"probe_site.py: {name} is from {a['created_at'][:10]}, too old: left out", file=sys.stderr)
            continue
        with zipfile.ZipFile(io.BytesIO(gh(f"repos/{REPO}/actions/artifacts/{a['id']}/zip"))) as z:
            if "probe.json" not in z.namelist():  # the job died before it wrote one
                continue
            try:
                steps = trim(json.loads(z.read("probe.json")))
            except (KeyError, TypeError, ValueError) as e:
                print(f"::warning::probe_site.py: {name} has a malformed probe.json ({e!r}): left out")
                continue
        cells.append(
            {
                **NAME.fullmatch(name).groupdict(),
                "date": a["created_at"][:10],
                "run": f"https://github.com/{REPO}/actions/runs/{a['workflow_run']['id']}",
                "steps": steps,
            }
        )
    cells.sort(key=lambda c: (tuple(map(int, c["python"].split("."))), c["os"]))
    return cells


def main(out: Path, today: date | None = None) -> None:
    """Write OUT with the newest probe result of every cell; warn, and write nothing, if there is none."""
    try:
        cells = collect(today or datetime.now(UTC).date())
    except Exception as e:  # noqa: BLE001 - whatever gh or the artifacts do, the site still deploys
        print(f"::warning::probe_site.py: no Python support table, {e!r}")
        return
    if not cells:
        print("::warning::probe_site.py: no current python-probe result, so no Python support table")
        return
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"cells": cells}, indent=1) + "\n")
    print(f"{out}: {len(cells)} probe results")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
