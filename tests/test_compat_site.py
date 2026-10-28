"""scripts/compat_site.py with `gh` stubbed out: which set it keeps for each compat job."""

import io
import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "compat_site.py"

# Answers each `gh api` call from a file in $FAKE; an artifact's zip is $FAKE/ID.zip.
GH = """#!/bin/sh
case "$*" in
*/workflows/compat.yml/runs*) cat "$FAKE/runs.json" ;;
*/jobs*) cat "$FAKE/jobs.json" ;;
*/zip) for a; do :; done; id=${a%/zip}; cat "$FAKE/${id##*/}.zip" ;;
*/artifacts*) cat "$FAKE/artifacts.jsonl" ;;
*) exit 1 ;;
esac
"""


def artifact(id_: int, name: str, created: str, branch: str = "main", *, expired: bool = False) -> dict:
    return {
        "id": id_,
        "name": name,
        "created_at": created,
        "expired": expired,
        "workflow_run": {"id": id_ * 100, "head_branch": branch},
    }


def run_site(tmp_path: Path, jobs: list[tuple[str, str]], artifacts: list[dict], *, ok: bool = True) -> dict:
    fake = tmp_path / "fake"
    fake.mkdir()
    (fake / "gh").write_text(GH)
    (fake / "gh").chmod(0o755)
    run = {"id": 7, "created_at": "2026-10-27T03:41:00Z", "html_url": "https://example.test/runs/7"}
    (fake / "runs.json").write_text(json.dumps({"workflow_runs": [run]}))
    (fake / "jobs.json").write_text(json.dumps({"jobs": [{"name": n, "conclusion": c} for n, c in jobs]}))
    (fake / "artifacts.jsonl").write_text("".join(json.dumps(a) + "\n" for a in artifacts))
    for a in artifacts:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("requirements.txt", f"brightway25==1.1.{a['id']}\nbw2calc==3.1.0\nnumpy==2.5.4\npytest==9.0.1\n")
            if "conda-forge" in a["name"]:
                z.writestr("pixi.toml", "[workspace]\n")
                z.writestr("pixi.lock", f"# set {a['id']}\n")
            else:
                z.writestr("pylock.toml", f"# set {a['id']}\n")
        (fake / f"{a['id']}.zip").write_bytes(buf.getvalue())
    site = tmp_path / "site"
    out = subprocess.run(
        [sys.executable, SCRIPT, site],
        env={
            **{k: v for k, v in os.environ.items() if k.startswith("COVERAGE_")},  # for `patch = ["subprocess"]`
            "PATH": f"{fake}:/usr/bin:/bin",
            "FAKE": str(fake),
            "GITHUB_REPOSITORY": "o/r",
        },
        capture_output=True,
        text=True,
        check=False,
    )
    if not ok:
        assert out.returncode != 0
        return {"stderr": out.stderr}
    assert out.returncode == 0, out.stderr
    return json.loads((site / "compat" / "status.json").read_text())


def test_keeps_each_jobs_newest_green_set_from_main(tmp_path: Path):
    jobs = [
        ("pre · Python 3.14 on ubuntu-latest", "failure"),
        ("floors · Python 3.12 on ubuntu-latest", "failure"),
        ("latest · Python 3.12 on ubuntu-latest", "success"),
        ("Set up job", "success"),  # not a matrix job
    ]
    artifacts = [  # newest first, as GitHub lists them
        artifact(9, "compat-green-pre-3.14-ubuntu-latest", "2026-10-27T04:00:00Z", branch="feat/x"),
        artifact(8, "compat-latest-3.12-ubuntu-latest", "2026-10-27T04:00:00Z"),  # kept whatever the result
        artifact(5, "compat-green-latest-3.12-ubuntu-latest", "2026-10-27T04:00:00Z"),
        artifact(4, "compat-green-latest-3.12-ubuntu-latest", "2026-10-26T04:00:00Z"),
        artifact(3, "compat-green-pre-3.14-ubuntu-latest", "2026-10-20T04:00:00Z", expired=True),
        artifact(2, "compat-green-pre-3.14-ubuntu-latest", "2026-10-19T04:00:00Z"),
    ]
    status = run_site(tmp_path, jobs, artifacts)
    assert status["date"] == "2026-10-27"
    latest, floors, pre = status["cells"]
    assert latest == {
        "column": "latest",
        "python": "3.12",
        "os": "ubuntu-latest",
        "today": "success",
        "green": {
            "date": "2026-10-27",
            "run": "https://github.com/o/r/actions/runs/500",
            "dir": "compat/latest-3.12-ubuntu-latest",
            "files": ["requirements.txt", "pylock.toml"],
            "versions": {"brightway25": "1.1.5", "bw2calc": "3.1.0", "numpy": "2.5.4"},
        },
    }
    assert floors["column"] == "floors"
    assert floors["green"] is None  # red for as long as artifacts last
    assert (pre["today"], pre["green"]["date"]) == ("failure", "2026-10-19")
    cell = tmp_path / "site" / "compat" / "latest-3.12-ubuntu-latest"
    assert (cell / "pylock.toml").read_text() == "# set 5\n"
    assert "pytest==9.0.1" in (cell / "requirements.txt").read_text()


def test_keeps_the_conda_forge_set_with_its_pixi_lock(tmp_path: Path):
    jobs = [
        ("conda-forge · Python 3.12 on ubuntu-latest", "success"),
        ("latest · Python 3.12 on ubuntu-latest", "success"),
    ]
    artifacts = [
        artifact(6, "compat-green-conda-forge-3.12-ubuntu-latest", "2026-10-27T04:00:00Z"),
        artifact(5, "compat-green-latest-3.12-ubuntu-latest", "2026-10-27T04:00:00Z"),
    ]
    latest, conda = run_site(tmp_path, jobs, artifacts)["cells"]
    assert latest["column"] == "latest"  # conda-forge sorts after the PyPI columns
    assert (conda["column"], conda["python"], conda["os"]) == ("conda-forge", "3.12", "ubuntu-latest")
    assert conda["green"]["files"] == ["requirements.txt", "pixi.toml", "pixi.lock"]
    cell = tmp_path / "site" / "compat" / "conda-forge-3.12-ubuntu-latest"
    assert (cell / "pixi.lock").read_text() == "# set 6\n"
    assert not (cell / "pylock.toml").exists()


def test_compat_workflow_names_jobs_and_green_sets_as_the_script_reads_them():
    workflow = (REPO / ".github" / "workflows" / "compat.yml").read_text()
    assert "name: ${{ matrix.column }} · Python ${{ matrix.python }} on ${{ matrix.os }}" in workflow
    assert "name: compat-green-${{ matrix.column }}-${{ matrix.python }}-${{ matrix.os }}" in workflow
    green = workflow.split("name: compat-green-")[0].rsplit("- uses:", 1)[1]
    assert "if: success()" in green


def test_index_shows_the_table(tmp_path: Path):
    status = {
        "date": "2026-10-27",
        "run": "https://example.test/runs/7",
        "cells": [
            {
                "column": "latest",
                "python": "3.12",
                "os": "ubuntu-latest",
                "today": "success",
                "green": {
                    "date": "2026-10-27",
                    "run": "https://example.test/runs/7",
                    "dir": "compat/latest-3.12-ubuntu-latest",
                    "files": ["requirements.txt", "pylock.toml"],
                    "versions": {"brightway25": "1.1.1", "numpy": "2.5.4"},
                },
            },
            {
                "column": "conda-forge",
                "python": "3.12",
                "os": "ubuntu-latest",
                "today": "success",
                "green": {
                    "date": "2026-10-27",
                    "run": "https://example.test/runs/7",
                    "dir": "compat/conda-forge-3.12-ubuntu-latest",
                    "files": ["requirements.txt", "pixi.toml", "pixi.lock"],
                    "versions": {"bw2calc": "3.1.0", "numpy": "2.5.4"},
                },
            },
            {"column": "floors", "python": "3.12", "os": "ubuntu-latest", "today": "failure", "green": None},
        ],
    }
    (tmp_path / "compat").mkdir()
    (tmp_path / "compat" / "status.json").write_text(json.dumps(status))
    subprocess.run([sys.executable, REPO / "scripts" / "site_index.py", tmp_path], check=True, capture_output=True)
    page = (tmp_path / "index.html").read_text()
    assert "Works together today" in page
    assert (
        '<td class="ok">green</td><td><a href="https://example.test/runs/7">2026-10-27</a></td><td>1.1.1</td>' in page
    )
    assert '<a href="compat/latest-3.12-ubuntu-latest/pylock.toml">pylock.toml</a>' in page
    assert '<td class="bad">failure</td><td>none kept</td>' in page
    # A package conda-forge lacks reads so in its row, and the row links the pixi files.
    assert "<td>not on conda-forge</td><td>3.1.0</td><td>not on conda-forge</td>" in page
    assert '<a href="compat/conda-forge-3.12-ubuntu-latest/pixi.lock">pixi.lock</a>' in page
    assert "conda-forge-3.12-ubuntu-latest/pylock.toml" not in page


def test_refuses_to_write_through_a_symlink_the_box_planted(tmp_path: Path):
    # The box can write site/, and this script runs on the host.
    outside = tmp_path / "outside"
    outside.mkdir()
    (tmp_path / "site").mkdir()
    (tmp_path / "site" / "compat").symlink_to(outside)
    job = "latest · Python 3.12 on ubuntu-latest"
    out = run_site(
        tmp_path, [(job, "success")], [artifact(1, "compat-green-latest-3.12-ubuntu-latest", "2026-10-27")], ok=False
    )
    assert "refusing" in out["stderr"]
    assert not any(outside.iterdir())
