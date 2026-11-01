"""scripts/compat_site.py with `gh` stubbed out: which set it keeps for each compat job."""

import importlib
import io
import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "compat_site.py"

# Answers each `gh api` call from a file in $FAKE; an artifact's zip is $FAKE/ID.zip.
GH = """#!/bin/sh
case "$*" in
*/workflows/compat.yml/runs*) cat "$FAKE/runs.json" ;;
*/workflows/compat.yml) echo '{"id": 11}' ;;
*repos/o/r) echo '{"id": 100}' ;;
*/jobs*) cat "$FAKE/jobs.json" ;;
*/runs/*) for a; do :; done; cat "$FAKE/run-${a##*/}.json" ;;
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
        "workflow_run": {"id": id_ * 100, "head_branch": branch, "repository_id": 100, "head_repository_id": 100},
    }


def run_site(tmp_path: Path, jobs: list[tuple[str, str]], artifacts: list[dict], *, ok: bool = True) -> dict:
    fake = tmp_path / f"fake{len(list(tmp_path.glob('fake*')))}"  # a second call keeps the first's archive
    fake.mkdir()
    (fake / "gh").write_text(GH)
    (fake / "gh").chmod(0o755)
    run = {"id": 7, "created_at": "2026-10-27T03:41:00Z", "html_url": "https://example.test/runs/7"}
    (fake / "runs.json").write_text(json.dumps({"workflow_runs": [run]}))
    (fake / "jobs.json").write_text(json.dumps({"jobs": [{"name": n, "conclusion": c} for n, c in jobs]}))
    (fake / "artifacts.jsonl").write_text("".join(json.dumps(a) + "\n" for a in artifacts))
    for a in artifacts:
        source = {
            "workflow_id": 11,
            "path": ".github/workflows/compat.yml",
            "event": "schedule",
            "head_branch": "main",
            "repository": {"id": 100},
            "head_repository": {"id": 100},
            "conclusion": "failure",
        } | a.get("source", {})
        (fake / f"run-{a['workflow_run']['id']}.json").write_text(json.dumps(source))
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            version = a.get("set", a["id"])  # a test may give two artifacts the same set
            z.writestr("requirements.txt", f"brightway25==1.1.{version}\nbw2calc==3.1.0\nnumpy==2.5.4\npytest==9.0.1\n")
            if "conda-forge" in a["name"]:
                z.writestr("pixi.toml", "[workspace]\n")
                z.writestr("pixi.lock", f"# set {a['id']}\n")
            else:
                z.writestr("pylock.toml", f"# set {version}\n")
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
            "dir": "compat/latest-3.12-ubuntu-latest/2026-10-27",
            "latest": "compat/latest-3.12-ubuntu-latest",
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


def test_dates_a_set_once_and_keeps_it_after_its_artifact_expires(tmp_path: Path):
    jobs = [("latest · Python 3.12 on ubuntu-latest", "success")]
    cell = tmp_path / "site" / "compat" / "latest-3.12-ubuntu-latest"
    run_site(tmp_path, jobs, [artifact(4, "compat-green-latest-3.12-ubuntu-latest", "2026-10-26T04:00:00Z")])
    # The next day's set is the same, so the command that names the 26th stays the newest.
    same = artifact(5, "compat-green-latest-3.12-ubuntu-latest", "2026-10-27T04:00:00Z") | {"set": 4}
    green = run_site(tmp_path, jobs, [same])["cells"][0]["green"]
    assert (green["date"], green["dir"]) == ("2026-10-27", "compat/latest-3.12-ubuntu-latest/2026-10-26")
    # A changed set gets its own folder; the undated one follows it, the 26th stays as it was.
    changed = artifact(6, "compat-green-latest-3.12-ubuntu-latest", "2026-10-28T04:00:00Z")
    green = run_site(tmp_path, jobs, [changed])["cells"][0]["green"]
    assert green["dir"] == "compat/latest-3.12-ubuntu-latest/2026-10-28"
    assert (cell / "pylock.toml").read_text() == "# set 6\n"
    assert (cell / "2026-10-26" / "pylock.toml").read_text() == "# set 4\n"
    # Red past the artifacts' 90 days: the archive still names the last green set.
    status = run_site(tmp_path, [("latest · Python 3.12 on ubuntu-latest", "failure")], [])
    green = status["cells"][0]["green"]
    assert (green["date"], green["run"]) == ("2026-10-28", "https://github.com/o/r/actions/runs/600")
    assert green["versions"]["brightway25"] == "1.1.6"


def test_a_second_set_on_the_same_day_leaves_the_first_one_alone(tmp_path: Path):
    jobs = [("latest · Python 3.12 on ubuntu-latest", "success")]
    cell = tmp_path / "site" / "compat" / "latest-3.12-ubuntu-latest"
    run_site(tmp_path, jobs, [artifact(4, "compat-green-latest-3.12-ubuntu-latest", "2026-10-26T04:00:00Z")])
    # A rerun at noon finds a new release: the morning's pinned command must still install set 4.
    noon = artifact(5, "compat-green-latest-3.12-ubuntu-latest", "2026-10-26T12:00:00Z")
    green = run_site(tmp_path, jobs, [noon])["cells"][0]["green"]
    assert green["dir"] == "compat/latest-3.12-ubuntu-latest/2026-10-26.2"
    assert (cell / "2026-10-26" / "pylock.toml").read_text() == "# set 4\n"
    assert (cell / "pylock.toml").read_text() == "# set 5\n"
    # The same set again the next day keeps the newest folder and names the newest passing run.
    again = artifact(6, "compat-green-latest-3.12-ubuntu-latest", "2026-10-27T04:00:00Z") | {"set": 5}
    green = run_site(tmp_path, jobs, [again])["cells"][0]["green"]
    assert green["dir"] == "compat/latest-3.12-ubuntu-latest/2026-10-26.2"
    assert green["run"] == "https://github.com/o/r/actions/runs/600"


def test_expired_artifact_keeps_the_latest_pass_of_an_unchanged_set(tmp_path: Path):
    jobs = [("latest · Python 3.12 on ubuntu-latest", "success")]
    run_site(tmp_path, jobs, [artifact(4, "compat-green-latest-3.12-ubuntu-latest", "2026-10-26T04:00:00Z")])
    same = artifact(5, "compat-green-latest-3.12-ubuntu-latest", "2026-10-27T04:00:00Z") | {"set": 4}
    before = run_site(tmp_path, jobs, [same])["cells"][0]["green"]
    after = run_site(tmp_path, [(jobs[0][0], "failure")], [])["cells"][0]["green"]
    assert after == before


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


def test_versions_match_names_as_uv_writes_them(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.syspath_prepend(str(SCRIPT.parent))
    versions = importlib.import_module("compat_site").versions
    reqs = "bw-graph-tools==0.6.1\n    # via brightway25\nbw_timex==1.2.0\nBW2Calc==3.1.0\nnumpy==2.5.4\n"
    assert versions(reqs) == {"bw2calc": "3.1.0", "bw_graph_tools": "0.6.1", "bw_timex": "1.2.0", "numpy": "2.5.4"}


def test_foreign_main_artifacts_do_not_become_tested_sets(tmp_path: Path):
    foreign = artifact(99, "compat-green-latest-3.12-ubuntu-latest", "2026-11-01")
    foreign["workflow_run"].update(repository_id=100, head_repository_id=200)
    status = run_site(tmp_path, [("latest · Python 3.12 on ubuntu-latest", "success")], [foreign])
    assert status["cells"][0]["green"] is None


@pytest.mark.parametrize(
    "source",
    [
        {"workflow_id": 22},
        {"path": ".github/workflows/ui.yml"},
        {"event": "pull_request"},
        {"head_branch": "feature"},
        {"repository": {"id": 200}},
        {"head_repository": {"id": 200}},
    ],
)
def test_untrusted_run_metadata_is_not_archived(tmp_path: Path, source: dict):
    candidate = artifact(99, "compat-green-latest-3.12-ubuntu-latest", "2026-11-01") | {"source": source}
    status = run_site(tmp_path, [("latest · Python 3.12 on ubuntu-latest", "success")], [candidate])
    assert status["cells"][0]["green"] is None


def test_artifact_run_provenance_is_looked_up_once(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.syspath_prepend(str(SCRIPT.parent))
    module = importlib.import_module("compat_site")
    calls = []

    def gh(path: str) -> bytes:
        calls.append(path)
        if path.endswith("compat.yml"):
            return b'{"id": 11}'
        if "/actions/runs/" not in path:
            return b'{"id": 100}'
        return json.dumps(
            {
                "workflow_id": 11,
                "path": ".github/workflows/compat.yml",
                "event": "schedule",
                "head_branch": "main",
                "repository": {"id": 100},
                "head_repository": {"id": 100},
                "status": "in_progress",
                "conclusion": None,
            }
        ).encode()

    monkeypatch.setattr(module, "gh", gh)
    trusted = module.GreenArtifacts()
    candidate = artifact(9, "compat-green-latest-3.12-ubuntu-latest", "2026-11-01")
    assert trusted(candidate)
    assert trusted(candidate)
    assert sum("/actions/runs/" in path for path in calls) == 1
