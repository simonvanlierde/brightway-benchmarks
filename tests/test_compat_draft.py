"""scripts/compat_draft.py on fixture files, and with `gh` stubbed out for the green fetch."""

import io
import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "compat_draft.py"

GH = """#!/bin/sh
case "$*" in
*/zip) cat "$FAKE/green.zip" ;;
*/artifacts*) cat "$FAKE/artifacts.jsonl" ;;
*) exit 1 ;;
esac
"""

PREV = "brightway25==1.1.0\nbw2calc==3.0.0\nnumpy==2.5.0\nscipy==1.16.0\n"
NOW = "brightway25==1.1.0\nbw2calc==3.1.0\nnumpy==2.5.0\nnewdep==1.0\n"


def run(
    tmp_path: Path, *, now: str | None, suites: str | None = None, prev: str | None = PREV, green: bool = False
) -> str:
    out = tmp_path / "3.12-suites"
    out.mkdir()
    if now is not None:
        (out / "requirements.txt").write_text(now)
    if suites is not None:
        (out / "suites.txt").write_text(suites)
    prev_path = tmp_path / "prev.txt"
    env = {
        **{k: v for k, v in os.environ.items() if k.startswith("COVERAGE_")},  # for `patch = ["subprocess"]`
        "PATH": f"{tmp_path}:/usr/bin:/bin",
        "GITHUB_RUN_ID": "42",
    }
    if prev is not None and not green:
        prev_path.write_text(prev)
    if green:
        (tmp_path / "gh").write_text(GH)
        (tmp_path / "gh").chmod(0o755)
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("requirements.txt", PREV)
        (tmp_path / "green.zip").write_bytes(buf.getvalue())
        a = {"id": 5, "expired": False, "workflow_run": {"head_branch": "main"}}
        (tmp_path / "artifacts.jsonl").write_text(json.dumps(a) + "\n")
        env |= {"FAKE": str(tmp_path), "GREEN": "compat-green-suites-3.12-ubuntu-latest"}
    subprocess.run([sys.executable, SCRIPT, out, prev_path], env=env, check=True)
    return (out / "issue-draft.md").read_text()


def test_failed_suite_names_nodes_and_changed_pins(tmp_path: Path) -> None:
    suites = "bw2data 4.8 passed\nbw2calc 3.1.0 failed\n    FAILED tests/test_a.py::test_x\n"
    text = run(tmp_path, now=NOW, suites=suites)
    assert "actions/runs/42" in text
    assert "FAILED tests/test_a.py::test_x" in text
    assert "bw2data 4.8 passed" not in text
    assert "- bw2calc: 3.0.0 -> 3.1.0" in text
    assert "- newdep: (new) -> 1.0" in text
    assert "- scipy: 1.16.0 -> (gone)" in text
    assert "numpy: " not in text.split("Pins changed")[1]


def test_resolve_failure_and_no_green_set(tmp_path: Path) -> None:
    text = run(tmp_path, now=None, prev=None)
    assert "resolve failed" in text
    assert "No green set to compare with" in text


def test_fetches_the_last_green_set(tmp_path: Path) -> None:
    text = run(tmp_path, now=NOW, green=True)
    assert "- bw2calc: 3.0.0 -> 3.1.0" in text
