"""Morning compatibility reports distinguish regressions from existing failures."""

import importlib
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


@pytest.fixture
def module(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    monkeypatch.syspath_prepend(str(SCRIPTS))
    return importlib.import_module("compat_changes")


def status(*cells: tuple[str, str], run: str = "7") -> dict:
    return {
        "date": "2026-10-31",
        "run": f"https://example.test/runs/{run}",
        "cells": [
            {"column": name, "python": "3.12", "os": "ubuntu-latest", "today": result, "green": None}
            for name, result in cells
        ],
    }


def test_names_new_failures_and_recoveries(module: ModuleType):
    before = status(("latest", "success"), ("suites", "failure"), run="6")
    after = status(("latest", "failure"), ("suites", "success"))
    report = module.report(before, after)
    assert "New failure: latest · Python 3.12 on ubuntu-latest (success → failure)" in report
    assert "Recovered: suites · Python 3.12 on ubuntu-latest (failure → success)" in report
    assert after["run"] in report
    assert before["run"] in report


def test_first_observation_is_not_a_regression(module: ModuleType):
    report = module.report(None, status(("suites", "failure")))
    assert "No previous snapshot" in report
    assert "Failure, no prior result: suites" in report
    assert "New failure:" not in report


def test_existing_failure_and_new_cell_are_distinct(module: ModuleType):
    before = status(("suites", "failure"))
    after = status(("suites", "failure"), ("floors", "timed_out"))
    report = module.report(before, after)
    assert "Still failing: suites" in report
    assert "Failure, no prior result: floors" in report
    assert "New failure:" not in report


def test_cancelled_skipped_and_missing_cells_are_not_failures_or_recoveries(module: ModuleType):
    before = status(("latest", "success"), ("floors", "failure"), ("suites", "failure"))
    after = status(("latest", "cancelled"), ("floors", "skipped"))
    report = module.report(before, after)
    assert "New failure:" not in report
    assert "Recovered:" not in report
    assert "Not evaluated: latest" in report
    assert "Not evaluated: floors" in report
    assert "Absent from current run: suites" in report


def test_cli_accepts_missing_baseline_and_fails_on_invalid_snapshot(tmp_path: Path):
    current = tmp_path / "current.json"
    current.write_text(json.dumps(status(("suites", "failure"))))
    command = [sys.executable, str(SCRIPTS / "compat_changes.py"), str(tmp_path / "missing.json"), str(current)]
    out = subprocess.run(command, capture_output=True, text=True, check=False)
    assert out.returncode == 0, out.stderr
    assert "Failure, no prior result: suites" in out.stdout
    current.write_text("{}")
    bad = subprocess.run(command, capture_output=True, text=True, check=False)
    assert bad.returncode != 0
    assert "Failure, no prior result:" not in bad.stdout


def test_cli_refuses_a_corrupt_baseline_without_replacing_it(tmp_path: Path):
    previous = tmp_path / "previous.json"
    previous.write_text("{broken")
    current = tmp_path / "current.json"
    current.write_text(json.dumps(status(("suites", "failure"))))
    out = subprocess.run(
        [sys.executable, str(SCRIPTS / "compat_changes.py"), str(previous), str(current)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert out.returncode != 0
    assert "Failure, no prior result:" not in out.stdout
    assert previous.read_text() == "{broken"


@pytest.mark.parametrize("snapshot", ["previous", "current"])
def test_duplicate_jobs_cannot_hide_a_failure(module: ModuleType, snapshot: str):
    before = status(("latest", "success"))
    after = status(("latest", "failure"))
    duplicate = status(("latest", "failure"), ("latest", "success"))
    if snapshot == "previous":
        before = duplicate
    else:
        after = duplicate
    with pytest.raises(ValueError, match="duplicate"):
        module.report(before, after)


@pytest.mark.parametrize(
    ("field", "value"),
    [("column", ""), ("python", 3.12), ("os", None), ("today", False), ("today", {}), ("today", "")],
)
def test_malformed_job_cannot_advance_a_baseline(module: ModuleType, field: str, value: object):
    current = status(("latest", "success"))
    current["cells"][0][field] = value
    with pytest.raises(ValueError, match=r"cell identity|cell conclusion"):
        module.report(None, current)


@pytest.mark.parametrize(
    ("field", "value"),
    [("date", "2026-02-30"), ("date", None), ("run", ""), ("run", 7), ("cells", {})],
)
def test_malformed_snapshot_metadata_is_rejected(module: ModuleType, field: str, value: object):
    current = status(("latest", "success"))
    current[field] = value
    with pytest.raises(ValueError, match=r"snapshot needs|day"):
        module.report(None, current)


@pytest.mark.parametrize("conclusion", [None, "neutral", "pending", "future_conclusion"])
def test_unevaluated_conclusions_remain_compatible(module: ModuleType, conclusion: str | None):
    current = status(("latest", "success"))
    current["cells"][0]["today"] = conclusion
    assert "Not evaluated: latest" in module.report(None, current)


def test_empty_snapshot_is_a_valid_absent_job_report(module: ModuleType):
    assert "Absent from current run: latest" in module.report(status(("latest", "success")), status())


def test_cli_rejects_duplicate_cells_without_printing_success(tmp_path: Path):
    previous = tmp_path / "previous.json"
    previous.write_text(json.dumps(status(("latest", "success"))))
    current = tmp_path / "current.json"
    current.write_text(json.dumps(status(("latest", "failure"), ("latest", "success"))))
    out = subprocess.run(
        [sys.executable, str(SCRIPTS / "compat_changes.py"), str(previous), str(current)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert out.returncode != 0
    assert not out.stdout
    assert "duplicate compatibility cell" in out.stderr
    assert json.loads(previous.read_text()) == status(("latest", "success"))
