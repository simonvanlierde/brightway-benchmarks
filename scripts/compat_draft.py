#!/usr/bin/env python3
"""Draft the text of an upstream issue for a compat job that failed.

Usage: compat_draft.py OUT PREV_REQS.

OUT is the job's output folder (requirements.txt, suites.txt). Writes OUT/issue-draft.md: the
package versions, what failed (the FAILED node IDs from suites.txt, or the resolve error when
there is no requirements.txt), the pins that changed since the job's last green set, and the run
URL. PREV_REQS is that set's requirements.txt. When the environment variable GREEN names the
job's artifact (`compat-green-COLUMN-PYTHON-OS`), it is fetched there first through `gh`, and
GITHUB_TOKEN is needed with `actions: read`. Green artifacts expire after 90 days, so a job red
for longer has no set to compare with, and the draft says so. Posting the draft stays with a person.
"""

import io
import json
import os
import sys
import zipfile
from pathlib import Path

from compat_site import GREEN, REPO, gh, versions


def fetch_green(name: str, dest: Path) -> None:
    """Save the requirements.txt of the newest unexpired NAME artifact from main, if there is one."""
    lines = gh("--paginate", f"repos/{REPO}/actions/artifacts?name={name}&per_page=100", "--jq", ".artifacts[] | @json")
    for a in map(json.loads, lines.splitlines()):
        if a["workflow_run"]["head_branch"] == "main" and not a["expired"]:
            with zipfile.ZipFile(io.BytesIO(gh(f"repos/{REPO}/actions/artifacts/{a['id']}/zip"))) as z:
                dest.write_bytes(z.read("requirements.txt"))
            return


def pins(requirements: str) -> dict[str, str]:
    """Every name==version in a requirements.txt."""
    return {k: v.split()[0] for k, v in (line.split("==", 1) for line in requirements.splitlines() if "==" in line)}


def draft(out: Path, prev: Path, run_url: str) -> str:
    """The issue text for the job whose files are in OUT."""
    reqs = out / "requirements.txt"
    text = [f"Compat job `{out.name}` failed: {run_url}", ""]
    if reqs.exists():
        now = reqs.read_text()
        text += ["Versions in the set:", *(f"- {k} {v}" for k, v in versions(now).items()), ""]
    else:
        text += ["The resolve failed: there is no requirements.txt (the job log has uv's or pixi's error).", ""]
    suites = out / "suites.txt"
    if suites.exists():
        bad = [ln for ln in suites.read_text().splitlines() if ln.startswith(" ") or not ln.endswith(" passed")]
        text += ["Failed:", "```", *bad, "```", ""]
    if not prev.exists():
        text += ["No green set to compare with: the last one expired (they are kept 90 days) or there is none.", ""]
    elif reqs.exists():
        old, new = pins(prev.read_text()), pins(now)
        changed = [
            f"- {k}: {old.get(k, '(new)')} -> {new.get(k, '(gone)')}"
            for k in sorted(old | new)
            if old.get(k) != new.get(k)
        ]
        text += ["Pins changed since the last green set:", *(changed or ["- none"]), ""]
    return "\n".join(text)


def main(out: Path, prev: Path) -> None:
    """Write OUT/issue-draft.md."""
    if green := os.environ.get("GREEN"):
        if not green.startswith(GREEN):
            msg = f"{green}: not a {GREEN}* artifact name"
            raise SystemExit(msg)
        fetch_green(green, prev)
    server = os.environ.get("GITHUB_SERVER_URL", "https://github.com")
    run_url = f"{server}/{REPO}/actions/runs/{os.environ.get('GITHUB_RUN_ID', '')}"
    (out / "issue-draft.md").write_text(draft(out, prev, run_url))


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
