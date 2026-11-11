#!/usr/bin/env python3
"""Collect the newest python-probe result of each Python and OS, for the site.

Usage: probe_site.py OUT_JSON.

The python-probe workflow uploads one `python-probe-PYTHON-OS` artifact per job (scripts/py_probe.py's
probe.json). The end-of-life Pythons run only on Mondays, so no single run holds every cell: this takes
each name's newest artifact from main's own python-probe runs, as compat_site.py does for the green sets,
and writes them to OUT_JSON. scripts/export_guidance.py reads that file. Needs `actions: read`.
"""

import io
import json
import re
import sys
import zipfile
from pathlib import Path

from compat_site import REPO, GreenArtifacts, gh

PREFIX = "python-probe-"
NAME = re.compile(r"python-probe-(?P<python>\d+\.\d+)-(?P<os>[\w-]+)")
# Enough of a step's error to name its cause; a uv build log runs to kilobytes.
ERROR = 500


def trim(probe: dict) -> list[dict]:
    """PROBE's steps, each error cut to ERROR characters."""
    return [{**s, **({"error": s["error"][:ERROR]} if "error" in s else {})} for s in probe["steps"]]


def main(out: Path) -> None:
    """Write OUT with the newest probe result of every cell."""
    # Newest first, so the first artifact of each name is its newest.
    lines = gh("--paginate", f"repos/{REPO}/actions/artifacts?per_page=100", "--jq", ".artifacts[] | @json")
    trusted = GreenArtifacts("python-probe.yml")
    newest: dict[str, dict] = {}
    for a in map(json.loads, lines.splitlines()):
        if a["name"].startswith(PREFIX) and NAME.fullmatch(a["name"]) and a["name"] not in newest and trusted(a):
            newest[a["name"]] = a
    cells = []
    for name, a in newest.items():
        with zipfile.ZipFile(io.BytesIO(gh(f"repos/{REPO}/actions/artifacts/{a['id']}/zip"))) as z:
            if "probe.json" not in z.namelist():  # the job died before it wrote one
                continue
            probe = json.loads(z.read("probe.json"))
        cells.append(
            {
                **NAME.fullmatch(name).groupdict(),
                "date": a["created_at"][:10],
                "run": f"https://github.com/{REPO}/actions/runs/{a['workflow_run']['id']}",
                "steps": trim(probe),
            }
        )
    cells.sort(key=lambda c: (tuple(map(int, c["python"].split("."))), c["os"]))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"cells": cells}, indent=1) + "\n")
    print(f"{out}: {len(cells)} probe results")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
