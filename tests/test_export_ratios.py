"""The comparison page's data: the newest ratio file per machine and a range summary per candidate."""

import importlib
import json
import shutil
from pathlib import Path
from types import ModuleType

import pytest
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
HOSTED = ROOT / "tests/fixtures/ratios/hosted"
UI_SCHEMA = json.loads((ROOT / "ui/schema/ratios.schema.json").read_text(encoding="utf-8"))


@pytest.fixture
def module(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    return importlib.import_module("export_ratios")


def export(module: ModuleType, ratios: Path | None, contributed: Path | None, out: Path) -> dict:
    """MODULE.export's data, which must be what the page's schema accepts."""
    data = module.export(ratios, contributed, out)
    validator = Draft202012Validator(UI_SCHEMA, format_checker=Draft202012Validator.FORMAT_CHECKER)
    assert [f"{list(e.absolute_path)}: {e.message}" for e in validator.iter_errors(data)] == []
    return data


def row(
    ratio: float | None, lo: float | None = None, hi: float | None = None, os: str = "Linux", tier: str = "hosted"
) -> dict:
    if ratio is None:
        return {"ratio": None, "ci95": None, "os": os, "tier": tier}
    return {"ratio": ratio, "ci95": [lo, hi], "os": os, "tier": tier}


def test_same_direction_is_a_range_of_speed_ups_over_the_clear_machines(module: ModuleType):
    rows = [row(0.4, 0.35, 0.45, "Linux"), row(0.33, 0.3, 0.34, "Darwin"), row(0.41, 0.4, 0.43, "Windows")]
    assert module.summary(rows) == {"direction": "faster", "text": "2.44 to 3.03x faster on 3 machines, 3 OSes"}


def test_machines_with_no_clear_difference_count_as_measured_but_not_in_the_range(module: ModuleType):
    rows = [row(1.2, 1.1, 1.3), row(0.98, 0.9, 1.05, "Windows"), row(1.5, 1.4, 1.6, "Linux")]
    assert module.summary(rows) == {
        "direction": "slower",
        "text": "1.20 to 1.50x slower on 2 machines, 1 OS; no clear difference on 1",
    }


def test_one_clear_machine_is_one_value_not_a_range(module: ModuleType):
    assert module.summary([row(19.88, 19.1, 20.5, "Windows")]) == {
        "direction": "slower",
        "text": "19.9x slower on 1 machine, 1 OS",
    }


def test_directions_that_disagree_depend_on_the_platform(module: ModuleType):
    rows = [row(0.5, 0.4, 0.6, "Linux"), row(1.2, 1.1, 1.3, "Windows"), row(1.3, 1.2, 1.4, "Darwin")]
    assert module.summary(rows) == {
        "direction": "mixed",
        "text": "Differs between machines: faster on 1 machine, slower on 2",
    }


def test_contributed_rows_count_only_when_no_verified_machine_measured(module: ModuleType):
    rows = [row(0.5, 0.45, 0.55), row(2.0, 1.8, 2.2, "Windows", "contributed"), row(0.4, 0.35, 0.45, tier="reference")]
    assert module.summary(rows) == {"direction": "faster", "text": "2.00 to 2.50x faster on 2 machines, 1 OS"}
    rows = [row(None), row(2.0, 1.8, 2.2, "Windows", "contributed"), row(1.0, 0.9, 1.1, tier="contributed")]
    assert module.summary(rows) == {
        "direction": "slower",
        "text": "2.00x slower on 1 machine, 1 OS; no clear difference on 1 (contributed machines only, unverified)",
    }


def test_an_interval_touching_one_is_no_clear_difference(module: ModuleType):
    rows = [row(1.05, 1.0, 1.1), row(0.95, 0.9, 1.0, "Windows")]
    assert module.summary(rows) == {"direction": "unclear", "text": "No clear difference on 2 machines"}


def test_missing_arms_are_left_out_never_counted_as_a_result(module: ModuleType):
    rows = [row(None, os="Darwin"), row(0.5, 0.45, 0.55)]
    assert module.summary(rows) == {"direction": "faster", "text": "2.00x faster on 1 machine, 1 OS"}
    assert module.summary([row(None), row(None, os="Windows")]) == {
        "direction": "none",
        "text": "Not measured on any machine",
    }


def test_row_verdicts(module: ModuleType):
    assert module.verdict(0.5, [0.4, 0.6]) == ("faster", "2.00x faster")
    assert module.verdict(1.03, [1.01, 1.05]) == ("slower", "3% slower")
    assert module.verdict(1.0, [0.95, 1.0]) == ("unclear", "No clear difference")
    assert module.verdict(None, None) == ("missing", "Not measured")


def hosted(tmp_path: Path) -> Path:
    archive = tmp_path / "ratios"
    shutil.copytree(HOSTED, archive / "hosted")
    return archive


def test_export_writes_one_row_per_machine_from_the_newest_file(module: ModuleType, tmp_path: Path):
    archive = hosted(tmp_path)
    old = json.loads((HOSTED / "2026-11-14/Linux.json").read_text(encoding="utf-8"))
    old["machine"] = "GitHub ubuntu24"
    old["created"] = "2026-11-07T14:00:00Z"
    # Run-id folders sort by name after the dated one, so only `created` picks the newest.
    (archive / "hosted/2026-11-07-99999999999").mkdir()
    (archive / "hosted/2026-11-07-99999999999/Linux.json").write_text(json.dumps(old), encoding="utf-8")

    out = export(module, archive, None, tmp_path / "data")

    written = json.loads((tmp_path / "data/ratios.json").read_text(encoding="utf-8"))
    assert written == out
    assert [m["name"] for m in out["machines"]] == ["GitHub ubuntu26", "GitHub macos26", "GitHub win25-vs2026"]
    linux = out["machines"][0]
    assert linux["tier"] == "hosted"
    assert linux["os"] == "Linux"
    assert linux["run"] == "https://github.com/simonvanlierde/brightway-benchmarks/actions/runs/43604589027"
    assert [m["os"] for m in out["machines"]] == ["Linux", "macOS", "Windows"]

    solvers = next(c for c in out["comparisons"] if c["id"] == "solvers")
    assert solvers["title"] == "Solver"
    assert solvers["case_name"] == "First score"
    pardiso = next(c for c in solvers["candidates"] if c["name"] == "pypardiso")
    assert pardiso["label"] == "PyPardiso against SuperLU"
    assert [r["machine"] for r in pardiso["rows"]] == [m["id"] for m in out["machines"]]
    mac = pardiso["rows"][1]
    assert mac["ratio"] is None
    assert mac["verdict"] == "missing"
    assert mac["missing"] == "bw2calc used umfpack, not pypardiso: pypardiso did not install"
    assert pardiso["summary"] == {"direction": "slower", "text": "1.21 to 19.9x slower on 2 machines, 2 OSes"}
    # The two releases ran on macOS and Windows only; Linux gets no row rather than a missing one.
    release = next(c for c in out["comparisons"] if c["id"] == "bw2calc-release")
    assert release["candidates"][0]["label"] == "bw2calc 3.1.0 against 3.0.0"
    assert [r["machine"] for r in release["candidates"][0]["rows"]] == ["hosted/macOS", "hosted/Windows"]


def test_contributed_and_reference_rows_keep_their_folder_s_tier(module: ModuleType, tmp_path: Path):
    archive = hosted(tmp_path)
    linux = json.loads((HOSTED / "2026-11-14/Linux.json").read_text(encoding="utf-8"))
    (archive / "reference").mkdir()
    (archive / "reference/2026-11-10.json").write_text(json.dumps({**linux, "tier": "reference", "machine": "Box"}))
    contributed = tmp_path / "contributed"
    (contributed / "lab-laptop").mkdir(parents=True)
    (contributed / "lab-laptop/2026-11-01.json").write_text(
        json.dumps({**linux, "tier": "contributed", "machine": "Old", "created": "2026-11-01T09:00:00Z"})
    )
    (contributed / "lab-laptop/2026-11-12.json").write_text(
        json.dumps({**linux, "tier": "contributed", "machine": "Lab laptop"})
    )
    # A contributed file that claims to be hosted is not trusted as either.
    (contributed / "liar").mkdir()
    (contributed / "liar/2026-11-12.json").write_text(json.dumps({**linux, "machine": "Liar"}))
    (contributed / "broken").mkdir()
    (contributed / "broken/2026-11-12.json").write_text('{"format": "bwbench-ratios/1"}')

    out = export(module, archive, contributed, tmp_path / "data")

    assert [(m["id"], m["tier"], m["name"]) for m in out["machines"]] == [
        ("reference", "reference", "Box"),
        ("hosted/Linux", "hosted", "GitHub ubuntu26"),
        ("hosted/macOS", "hosted", "GitHub macos26"),
        ("hosted/Windows", "hosted", "GitHub win25-vs2026"),
        ("contributed/lab-laptop", "contributed", "Lab laptop"),
    ]
    assert out["machines"][-1]["run"] is None
    # The contributed lab laptop has a row but no say in the summary.
    pardiso = next(
        k for c in out["comparisons"] if c["id"] == "solvers" for k in c["candidates"] if k["name"] == "pypardiso"
    )
    assert [r["machine"] for r in pardiso["rows"]][-1] == "contributed/lab-laptop"
    assert pardiso["summary"]["text"].endswith("slower on 3 machines, 2 OSes")


def test_no_ratio_files_write_nothing(module: ModuleType, tmp_path: Path):
    assert module.export(tmp_path / "absent", tmp_path / "also-absent", tmp_path / "data") is None
    assert not (tmp_path / "data/ratios.json").exists()


def test_the_ui_fixture_is_the_export_of_the_hosted_fixtures(module: ModuleType, tmp_path: Path):
    """ui/README.md says how to refresh ui/test/fixtures/real/ratios.json when this fails."""
    out = export(module, hosted(tmp_path), None, tmp_path / "data")
    assert json.loads((ROOT / "ui/test/fixtures/real/ratios.json").read_text(encoding="utf-8")) == out


def test_an_empty_missing_reason_reads_as_empty(module: ModuleType):
    # The file schema allows "missing": "", so the reason has no first line.
    comparison = {"baseline": "superlu", "arms": {"superlu": {"missing": None}, "pypardiso": {"missing": ""}}}
    assert module.reason(comparison, {"candidate": "pypardiso", "missing": ""}) == ""


def test_a_file_that_breaks_the_export_is_skipped_with_a_warning(
    module: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    linux = json.loads((HOSTED / "2026-11-14/Linux.json").read_text(encoding="utf-8"))
    contributed = tmp_path / "contributed"
    for name in ("good", "bad-check", "bad-build"):
        (contributed / name).mkdir(parents=True)
        doc = {**linux, "tier": "contributed", "machine": name}
        (contributed / name / "2026-11-12.json").write_text(json.dumps(doc), encoding="utf-8")
    real_problems = module.problems

    def problems(doc: dict) -> list[str]:
        if doc["machine"] == "bad-check":
            message = "arch"
            raise KeyError(message)
        return real_problems(doc)

    bad = json.loads((contributed / "bad-build/2026-11-12.json").read_text(encoding="utf-8"))
    bad["comparisons"][0]["case"] = "bench_x.Y.time_crash"
    (contributed / "bad-build/2026-11-12.json").write_text(json.dumps(bad), encoding="utf-8")
    real_reason = module.reason

    def crash(comparison: dict, ratio: dict) -> str | None:
        if comparison["case"] == "bench_x.Y.time_crash":
            message = "boom"
            raise TypeError(message)
        return real_reason(comparison, ratio)

    monkeypatch.setattr(module, "problems", problems)
    monkeypatch.setattr(module, "reason", crash)

    out = export(module, None, contributed, tmp_path / "data")

    assert [m["name"] for m in out["machines"]] == ["good"]
    err = capsys.readouterr().err
    assert "bad-check/2026-11-12.json: KeyError" in err
    assert "skipped contributed/bad-build: TypeError: boom" in err


def test_a_file_outside_a_checkout_with_integer_params_still_loads(module: ModuleType, tmp_path: Path):
    linux = json.loads((HOSTED / "2026-11-14/Linux.json").read_text(encoding="utf-8"))
    linux["source"]["commit"] = None
    linux["comparisons"][0]["params"]["rounds"] = 2
    (tmp_path / "contributed/lab").mkdir(parents=True)
    doc = {**linux, "tier": "contributed", "machine": "Lab"}
    (tmp_path / "contributed/lab/2026-11-12.json").write_text(json.dumps(doc), encoding="utf-8")

    out = export(module, None, tmp_path / "contributed", tmp_path / "data")

    assert out["machines"][0]["commit"] is None
    assert {"name": "rounds", "value": "2", "note": None} in out["comparisons"][0]["params"]


def test_one_comparison_with_two_param_sets_gets_two_keys(module: ModuleType, tmp_path: Path):
    linux = json.loads((HOSTED / "2026-11-14/Linux.json").read_text(encoding="utf-8"))
    (tmp_path / "contributed/lab").mkdir(parents=True)
    medium = {**linux, "tier": "contributed", "machine": "Lab"}
    medium["comparisons"] = [{**c, "params": {**c["params"], "size": "medium"}} for c in linux["comparisons"]]
    (tmp_path / "contributed/lab/2026-11-12.json").write_text(json.dumps(medium), encoding="utf-8")

    out = export(module, hosted(tmp_path), tmp_path / "contributed", tmp_path / "data")

    keys = [c["key"] for c in out["comparisons"]]
    assert len(set(keys)) == len(keys)
    solvers = [c["key"] for c in out["comparisons"] if c["id"] == "solvers"]
    assert solvers == [
        "solvers-bench-lca-singlescore-time-first-score-cls-lca-size-smoke-superlu",
        "solvers-bench-lca-singlescore-time-first-score-cls-lca-size-medium-superlu",
    ]


def test_small_differences_read_as_percentages_and_large_ones_as_whole_multiples(module: ModuleType):
    assert module.verdict(0.9996, [0.9994, 0.9998]) == ("faster", "0.04% faster")
    assert module.verdict(0.98, [0.97, 0.99]) == ("faster", "2% faster")
    assert module.verdict(1.004, [1.002, 1.006]) == ("slower", "0.4% slower")
    assert module.verdict(1000.4, [990.0, 1010.0]) == ("slower", "1000x slower")
    assert module.verdict(1234.0, [1200.0, 1300.0]) == ("slower", "1234x slower")
    assert module.summary([row(1.04, 1.02, 1.06), row(1.5, 1.4, 1.6, "Windows")]) == {
        "direction": "slower",
        "text": "4% to 1.50x slower on 2 machines, 2 OSes",
    }
