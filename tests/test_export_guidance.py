"""The setup view uses published checks and comparable benchmark measurements."""

import importlib
import json
import shutil
from pathlib import Path
from types import ModuleType

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from jsonschema import Draft202012Validator, ValidationError
from jsonschema.protocols import Validator

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def module(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    return importlib.import_module("export_guidance")


def cell(
    column: str = "latest", os: str = "ubuntu-latest", outcome: str = "success", files: list[str] | None = None
) -> dict:
    return {
        "column": column,
        "python": "3.12",
        "os": os,
        "today": outcome,
        "green": {
            "date": "2026-10-30",
            "run": "https://example.test/runs/6",
            "dir": f"compat/{column}-3.12-{os}/2026-10-28",
            "latest": f"compat/{column}-3.12-{os}",
            "files": ["requirements.txt", "pylock.toml"] if files is None else files,
            "versions": {"brightway25": "1.1.1", "bw2calc": "3.1.0"},
        },
    }


def snapshot(tmp_path: Path, cells: list[dict]) -> Path:
    path = tmp_path / "status.json"
    path.write_text(json.dumps({"date": "2026-10-31", "run": "https://example.test/runs/7", "cells": cells}))
    return path


def validator() -> Validator:
    return Draft202012Validator(json.loads((ROOT / "ui/schema/guidance.schema.json").read_text()))


def test_failed_latest_keeps_last_passing_set_and_its_date(module: ModuleType, tmp_path: Path):
    out = module.export(snapshot(tmp_path, [cell(outcome="failure")]), tmp_path / "data", "https://example.test/bench/")
    check = out["checks"][0]
    assert check["status"] == "failure"
    assert check["lastPassed"]["date"] == "2026-10-30"
    folder = "https://example.test/bench/compat/latest-3.12-ubuntu-latest/"
    assert check["lastPassed"]["pinned"] == "2026-10-28"
    assert check["lastPassed"]["files"][0] == {
        "label": "requirements.txt",
        "url": folder + "2026-10-28/requirements.txt",
        "latest": folder + "requirements.txt",
    }
    assert check["lastPassed"]["installs"][0] == {
        "manager": "uv",
        "command": f"uv add brightway25 bw_graph_tools bw_timex -c {folder}2026-10-28/requirements.txt",
        "latest": f"uv add brightway25 bw_graph_tools bw_timex -c {folder}requirements.txt",
    }
    assert out["platforms"][0]["defaultCheck"] == check["id"]
    assert json.loads((tmp_path / "data" / "guidance.json").read_text()) == out
    validator().validate(out)


def test_scope_and_installation_follow_the_actual_check(module: ModuleType, tmp_path: Path):
    conda = cell("conda-forge", files=["requirements.txt", "environment.yml", "pixi.toml", "pixi.lock"])
    suite = cell("suites", outcome="failure")
    suite["green"] = None
    out = module.export(
        snapshot(tmp_path, [cell(os="macos-latest"), conda, suite]), tmp_path / "data", "https://example.test/"
    )
    mac, conda, suite = out["checks"]
    assert [i["manager"] for i in mac["lastPassed"]["installs"]] == ["uv", "pip"]
    assert "solver" in " ".join(mac["caveats"]).lower()
    labels = [file["label"] for file in conda["lastPassed"]["files"]]
    assert labels == ["environment.yml", "pixi.toml", "pixi.lock", "requirements.txt"]
    folder = "https://example.test/compat/conda-forge-3.12-ubuntu-latest/2026-10-28/"
    assert [(i["manager"], i["command"]) for i in conda["lastPassed"]["installs"]] == [
        ("conda", f"conda env update -n brightway-tested -f {folder}environment.yml --prune"),
        ("pixi", f"curl -fL -O {folder}pixi.toml -O {folder}pixi.lock && pixi install --frozen"),
    ]
    assert "bw_timex" in " ".join(conda["caveats"])
    assert suite["kind"] == "suites"
    assert "lastPassed" not in suite
    validator().validate(out)


def test_missing_files_do_not_offer_an_install_or_default(module: ModuleType, tmp_path: Path):
    out = module.export(snapshot(tmp_path, [cell(files=[])]), tmp_path / "data", "https://example.test/")
    assert out["checks"][0]["lastPassed"]["installs"] == []
    assert "defaultCheck" not in out["platforms"][0]


def test_a_set_without_a_dated_folder_is_named_where_it_is(module: ModuleType, tmp_path: Path):
    old = cell()
    old["green"]["dir"] = old["green"].pop("latest")  # a status.json from before the compat archive
    passed = module.export(snapshot(tmp_path, [old]), tmp_path / "data", "https://example.test/")["checks"][0]
    passed = passed["lastPassed"]
    assert "pinned" not in passed
    assert passed["files"][0] == {
        "label": "requirements.txt",
        "url": "https://example.test/compat/latest-3.12-ubuntu-latest/requirements.txt",
    }
    assert "latest" not in passed["installs"][0]


def test_missing_status_removes_only_a_regular_stale_guidance_file(
    module: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    data = tmp_path / "data"
    data.mkdir()
    out = data / "guidance.json"
    out.write_text("stale")
    assert module.export(tmp_path / "missing", data, "https://example.test/") is None
    assert not out.exists()
    assert "no setup guidance" in capsys.readouterr().err
    target = tmp_path / "target"
    target.write_text("keep")
    out.symlink_to(target)
    with pytest.raises(ValueError, match="symlink"):
        module.export(tmp_path / "missing", data, "https://example.test/")
    assert target.read_text() == "keep"


def test_unsafe_source_paths_and_urls_are_rejected(module: ModuleType, tmp_path: Path):
    bad = cell()
    bad["green"]["dir"] = "compat/../../elsewhere"
    with pytest.raises(ValueError, match="under compat"):
        module.export(snapshot(tmp_path, [bad]), tmp_path / "data", "https://example.test/")
    with pytest.raises(ValueError, match="HTTP"):
        module.export(snapshot(tmp_path, [cell()]), tmp_path / "data", "javascript:alert(1)")
    out = module.export(snapshot(tmp_path, [cell()]), tmp_path / "data", "https://example.test/")
    out["checks"][0]["run"] = "javascript:alert(1)"
    with pytest.raises(ValidationError):
        validator().validate(out)


def test_solver_comparison_uses_values_from_one_machine_and_matching_release(module: ModuleType, tmp_path: Path):
    data = tmp_path / "data"
    data.mkdir()
    index = {
        "groups": [{"id": "calc", "name": "bw2calc"}, {"id": "conda", "name": "bw2calc-conda"}],
        "machines": [{"id": "machine", "name": "Pinned test machine"}, {"id": "other", "name": "Other test machine"}],
        "environments": [
            {"id": "p", "group": "calc", "label": "PyPardiso"},
            {"id": "s", "group": "calc", "label": "SuperLU"},
            {"id": "u", "group": "conda", "label": "UMFPACK", "name": "rattler-py3.12-scikit-umfpack"},
        ],
        "benchmarks": [
            {"id": "b", "group": "calc", "name": "bench_lca.SingleScore.time_first_score"},
            {"id": "c", "group": "conda", "name": "bench_lca.SingleScore.time_first_score"},
        ],
        "cases": [
            {"id": "p", "benchmark": "b", "environment": "p", "params": ["'ecoinvent'", "'LCA'"]},
            {"id": "s", "benchmark": "b", "environment": "s", "params": ["'ecoinvent'", "'LCA'"]},
            {"id": "u", "benchmark": "c", "environment": "u", "params": ["'ecoinvent'", "'LCA'"]},
        ],
        "commits": [
            {"id": "old", "group": "calc", "date": "2026-10-01", "release": "2.5.0"},
            {"id": "new", "group": "calc", "date": "2026-10-18", "release": "3.1.0"},
            {"id": "new", "group": "conda", "date": "2026-10-18", "release": "3.1.0"},
        ],
        "reports": [
            {"path": "calc.json", "group": "calc", "machine": "machine", "commit": "new"},
            {"path": "conda.json", "group": "conda", "machine": "other", "commit": "new"},
        ],
    }
    (data / "index.json").write_text(json.dumps(index))
    (data / "calc.json").write_text(json.dumps({"p": {"latency": {"value": 10e9}}, "s": {"latency": {"value": 27e9}}}))
    (data / "conda.json").write_text(json.dumps({"u": {"latency": {"value": 2e9}}}))
    assert module.solver_comparison(data) is None
    index["reports"][1]["machine"] = "machine"
    (data / "index.json").write_text(json.dumps(index))
    result = module.solver_comparison(data)
    assert {r["label"]: r["value"] for r in result["rows"]} == {
        "PyPardiso": 10e9,
        "SuperLU": 27e9,
        "UMFPACK · conda-forge": 2e9,
    }
    assert all("machine=machine" in row["href"] and row["unit"] == "ns" for row in result["rows"])
    assert "3.1.0" in result["context"]
    (data / "conda.json").unlink()
    assert module.solver_comparison(data) is None


def solver_data(tmp_path: Path) -> Path:
    """One machine with all three solvers measured on bw2calc 3.1.0 and on 2.5.0."""
    data = tmp_path / "data"
    data.mkdir()
    index = {
        "groups": [{"id": "calc", "name": "bw2calc"}, {"id": "conda", "name": "bw2calc-conda"}],
        "machines": [{"id": "machine", "name": "Pinned test machine"}],
        "environments": [
            {"id": "p", "group": "calc", "label": "PyPardiso"},
            {"id": "s", "group": "calc", "label": "SuperLU"},
            {"id": "u", "group": "conda", "label": "UMFPACK", "name": "rattler-py3.12-scikit-umfpack"},
            {"id": "m", "group": "conda", "label": "UMFPACK", "name": "rattler-py3.12-mkl"},
        ],
        "benchmarks": [
            {"id": "b", "group": "calc", "name": "bench_lca.SingleScore.time_first_score"},
            {"id": "c", "group": "conda", "name": "bench_lca.SingleScore.time_first_score"},
        ],
        "cases": [
            {"id": "p", "benchmark": "b", "environment": "p", "params": ["'ecoinvent'", "'LCA'"]},
            {"id": "s", "benchmark": "b", "environment": "s", "params": ["'ecoinvent'", "'LCA'"]},
            {"id": "u", "benchmark": "c", "environment": "u", "params": ["'ecoinvent'", "'LCA'"]},
            {"id": "m", "benchmark": "c", "environment": "m", "params": ["'ecoinvent'", "'LCA'"]},
        ],
        "commits": [
            {"id": "old", "group": "calc", "date": "2026-10-01", "release": "2.5.0"},
            {"id": "old", "group": "conda", "date": "2026-10-01", "release": "2.5.0"},
            {"id": "new", "group": "calc", "date": "2026-10-18", "release": "3.1.0"},
            {"id": "new", "group": "conda", "date": "2026-10-18", "release": "3.1.0"},
        ],
        "reports": [
            {"path": f"{group}-{commit}.json", "group": group, "machine": "machine", "commit": commit}
            for group in ("calc", "conda")
            for commit in ("old", "new")
        ],
    }
    (data / "index.json").write_text(json.dumps(index))
    for commit, scale in (("old", 2), ("new", 1)):
        calc = {"p": {"latency": {"value": 10e9 * scale}}, "s": {"latency": {"value": 27e9 * scale}}}
        conda = {"u": {"latency": {"value": 2e9 * scale}}, "m": {"latency": {"value": 1e9}}}
        (data / f"calc-{commit}.json").write_text(json.dumps(calc))
        (data / f"conda-{commit}.json").write_text(json.dumps(conda))
    return data


def test_solver_comparison_takes_the_latest_release_and_never_falls_back(module: ModuleType, tmp_path: Path):
    data = solver_data(tmp_path)
    result = module.solver_comparison(data)
    # The MKL build of UMFPACK is not the conda-forge row, and 2.5.0's slower values stay out.
    assert {r["label"]: r["value"] for r in result["rows"]} == {
        "UMFPACK · conda-forge": 2e9,
        "PyPardiso": 10e9,
        "SuperLU": 27e9,
    }
    assert "3.1.0" in result["context"]
    # With one solver missing from the latest release, an older complete set is not shown instead.
    (data / "conda-new.json").write_text(json.dumps({"u": {"latency": {"value": float("nan")}}}))
    assert module.solver_comparison(data) is None
    (data / "conda-new.json").write_text(json.dumps({"u": {"latency": {"value": 0}}}))
    assert module.solver_comparison(data) is None


def test_solver_comparison_refuses_a_report_outside_the_data_directory(module: ModuleType, tmp_path: Path):
    data = solver_data(tmp_path)
    index = json.loads((data / "index.json").read_text())
    index["reports"][1]["path"] = "../calc-new.json"  # a latest-release report: older ones are not read
    (data / "index.json").write_text(json.dumps(index))
    with pytest.raises(ValueError, match="inside the data directory"):
        module.solver_comparison(data)


def test_labels_cover_every_compat_column(module: ModuleType):
    compat_site = importlib.import_module("compat_site")
    assert set(module.LABELS) == set(compat_site.COLUMNS)
    assert set(module.DESCRIPTIONS) == set(compat_site.COLUMNS)


@given(
    files=st.lists(
        st.sampled_from(["requirements.txt", "pylock.toml", "environment.yml", "pixi.toml", "pixi.lock"]), unique=True
    ),
    outcome=st.sampled_from(["success", "failure", "cancelled", "skipped", None]),
)
@settings(max_examples=20, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_exported_check_variants_follow_the_contract(
    module: ModuleType, tmp_path: Path, files: list[str], outcome: str | None
):
    # Each example overwrites the same snapshot; no state from a prior example is read.
    source = cell(files=files)
    source["today"] = outcome
    out = module.export(snapshot(tmp_path, [source]), tmp_path / "data", "https://example.test/")
    validator().validate(out)
    assert out["checks"][0]["status"] == (outcome or "unknown")


@pytest.mark.parametrize("os_name", ["ubuntu-latest", "macos-latest", "windows-latest"])
@pytest.mark.parametrize("column", ["latest", "floors", "pre", "suites"])
def test_install_includes_all_checked_runtime_roots(module: ModuleType, tmp_path: Path, os_name: str, column: str):
    out = module.export(snapshot(tmp_path, [cell(column, os_name)]), tmp_path / "data", "https://example.test/")
    commands = [i["command"] for i in out["checks"][0]["lastPassed"]["installs"]]
    assert all(" brightway25 bw_graph_tools bw_timex -c https://" in c for c in commands)
    assert len(commands) == 2


def test_committed_ui_fixture_is_what_the_exporter_writes(module: ModuleType, tmp_path: Path):
    # The browser tests read this fixture. When this fails, refresh it with
    # `python3 scripts/export_guidance.py ui/test/fixtures/compat/status.json ui/test/fixtures/real`.
    fixtures = ROOT / "ui/test/fixtures"
    data = tmp_path / "real"
    shutil.copytree(fixtures / "real", data)
    module.export(fixtures / "compat/status.json", data)
    assert (data / "guidance.json").read_text() == (fixtures / "real/guidance.json").read_text()


@pytest.mark.parametrize(
    ("column", "meaning"),
    [
        ("latest", "latest stable releases"),
        ("floors", "lowest allowed versions"),
        ("pre", "pre-release packages"),
        ("conda-forge", "from conda-forge"),
        ("suites", "upstream package test suites"),
    ],
)
def test_check_description_explains_its_actual_column(module: ModuleType, tmp_path: Path, column: str, meaning: str):
    out = module.export(snapshot(tmp_path, [cell(column)]), tmp_path / "data", "https://example.test/")
    check = out["checks"][0]
    assert meaning in check["description"]
    assert check["description"] != check["coverage"]
    validator().validate(out)
    del check["description"]
    validator().validate(out)  # Existing guidance remains valid without the optional explanation.
