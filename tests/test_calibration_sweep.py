"""Calibration guards and complete output remain mandatory when an experiment fails."""

import importlib
import json
import subprocess
import sys
from concurrent.futures.process import BrokenProcessPool
from dataclasses import asdict, replace
from pathlib import Path
from types import ModuleType

import numpy as np
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from scipy import sparse

from bwbench import synth

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


@pytest.fixture
def sweep(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.syspath_prepend(str(SCRIPTS))
    module = importlib.import_module("calibration_sweep")
    monkeypatch.setitem(module.CASES, "denser", {"back": 0.2})  # a second case, as a generator change adds
    return module


@pytest.fixture
def target():
    data = json.loads((synth.PROFILES_DIR / "ecoinvent-3.12-cutoff.json").read_text())
    return synth.Stats(**data["stats"])


def row(case: str, seed: int, target: synth.Stats) -> dict:
    overrides = {"baseline": {}, "denser": {"back": 0.2}}[case]
    return json.loads(
        json.dumps(
            {
                "case": case,
                "seed": seed,
                "stats": asdict(target),
                "overrides": overrides,
                "profile": asdict(synth.profile("ecoinvent", **overrides)),
                "input_overlap_by_band": {"2-4": {"overlap": 0.5, "pairs_share": 0.8}},
            }
        )
    )


def test_complete_passing_cases_are_the_only_success(sweep: ModuleType, target: synth.Stats, tmp_path: Path):
    output = tmp_path / "report.json"
    seen = []

    def worker(case: str, seed: int):
        seen.append((case, seed))
        # The on-disk file cannot claim success while another seed is outstanding.
        assert json.loads(output.read_text())["passed"] is False
        return row(case, seed, target)

    report = sweep.run_sweep(["baseline", "denser"], [0, 1], worker, target, output)
    assert seen == [("baseline", 0), ("baseline", 1), ("denser", 0), ("denser", 1)]
    assert report["complete"] is True
    assert report["passed"] is True
    assert json.loads(output.read_text()) == report
    assert report["cases"]["denser"] == {"back": 0.2}


def test_worker_crash_cannot_be_a_success(sweep: ModuleType, target: synth.Stats, tmp_path: Path):
    def worker(case: str, seed: int):
        if seed == 1:
            msg = "worker terminated abruptly"
            raise BrokenProcessPool(msg)
        return row(case, seed, target)

    report = sweep.run_sweep(["baseline"], [0, 1, 2], worker, target, tmp_path / "report.json")
    assert report["passed"] is False
    assert report["complete"] is False
    assert report["results"][1]["error"] == "BrokenProcessPool: worker terminated abruptly"
    assert len(report["results"]) == 3


def test_scc_failure_is_reported_with_its_threshold(sweep: ModuleType, target: synth.Stats, tmp_path: Path):
    changed = replace(target, loops=target.loops | {"largest": round(target.products * 0.5)})
    report = sweep.run_sweep(["denser"], [0], lambda c, s: row(c, s, changed), target, tmp_path / "report.json")
    assert report["complete"] is True
    assert report["passed"] is False
    assert len(report["results"][0]["failures"]) == 1
    assert "SCC share" in report["results"][0]["failures"][0]
    assert "abs 0.12" in report["results"][0]["failures"][0]


@pytest.mark.parametrize("damage", ["wrong seed", "missing stats", "missing transpose", "nonfinite"])
def test_incomplete_or_nonfinite_worker_output_fails(
    sweep: ModuleType, target: synth.Stats, tmp_path: Path, damage: str
):
    def worker(case: str, seed: int):
        data = row(case, seed, target)
        if damage == "wrong seed":
            data["seed"] = 9
        elif damage == "missing stats":
            del data["stats"]["entries"]
        elif damage == "missing transpose":
            del data["stats"]["lu_fill"]["COLAMD (A^T)"]
        else:
            data["stats"]["same_location_share"] = float("nan")
        return data

    report = sweep.run_sweep(["baseline"], [0], worker, target, tmp_path / "report.json")
    assert report["passed"] is False
    assert report["complete"] is False
    assert "error" in report["results"][0]


def test_small_real_measurement_has_both_fills_and_labels(sweep: ModuleType):
    data = sweep.measure_case("baseline", 0, products=100)
    stats = data["stats"]
    assert set(stats["lu_fill"]) == {"COLAMD", "COLAMD (A^T)"}
    assert all(v > 0 for v in stats["lu_fill"].values())
    assert stats["same_location_share"] is not None
    assert stats["same_sector_share"] is not None
    assert stats["overlap_by_band"]
    assert data["overrides"] == {"products": 100}


def test_cli_keeps_failed_guard_output_and_returns_nonzero(tmp_path: Path):
    output = tmp_path / "report.json"
    run = subprocess.run(
        [
            sys.executable,
            str(SCRIPTS / "calibration_sweep.py"),
            "--products",
            "100",
            "--cases",
            "baseline",
            "--seeds",
            "0",
            "--output",
            str(output),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert run.returncode == 1, run.stderr
    report = json.loads(output.read_text())
    assert report["complete"] is True
    assert report["passed"] is False
    assert any("products:" in error for error in report["results"][0]["failures"])


@pytest.mark.parametrize("args", [["--seeds", "0", "0"], ["--seeds", "-1"], ["--products", "1"]])
def test_invalid_sweep_selection_is_rejected(sweep: ModuleType, args: list[str]):
    with pytest.raises(SystemExit) as exc:
        sweep.main(args)
    assert exc.value.code == 2


def test_input_overlap_uses_columns_not_supplier_rows(sweep: ModuleType):
    a = sparse.csc_matrix(np.array([[1.0, -0.5, -0.2], [-0.4, -1.0, 0.0], [0.0, 0.0, 1.0]]))
    assert sweep.input_overlap(a) == {"2-4": {"overlap": 7 / 12, "pairs_share": 1.0}}


@pytest.mark.parametrize(("cases", "seeds"), [([], [0]), (["baseline"], []), (["baseline"], [0, 0])])
def test_empty_or_duplicate_requests_cannot_succeed(
    sweep: ModuleType, target: synth.Stats, tmp_path: Path, cases: list[str], seeds: list[int]
):
    with pytest.raises(ValueError, match="nonempty, unique"):
        sweep.run_sweep(cases, seeds, lambda c, s: row(c, s, target), target, tmp_path / "report.json")


@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(st.lists(st.lists(st.booleans(), min_size=5, max_size=5), min_size=5, max_size=5))
def test_overlap_agrees_with_explicit_pairs(sweep: ModuleType, values: list[list[bool]]):
    a = sparse.csc_matrix(np.asarray(values, dtype=float) + np.eye(5))
    columns = [set(a.indices[a.indptr[j] : a.indptr[j + 1]]) for j in range(5)]
    all_pairs = sum(len(c) ** 2 for c in columns)
    expected = {}
    for low, high in synth.OVERLAP_BANDS:
        selected = [c for c in columns if low <= len(c) <= high]
        count = sum(len(c) ** 2 for c in selected)
        if count:
            pairs = {(i, j) for c in selected for i in c for j in c}
            label = f"{low}+" if high == synth.OVERLAP_BANDS[-1][1] else f"{low}-{high}"
            expected[label] = {"overlap": len(pairs) / count, "pairs_share": count / all_pairs}
    assert sweep.input_overlap(a) == expected


def test_relative_guard_uses_target_not_the_larger_observation(sweep: ModuleType, target: synth.Stats):
    got = replace(target, entries=327557)
    assert any(error.startswith("entries:") for error in sweep.calibration_failures(got, target))
    target = replace(target, entries=10000)
    assert not sweep.calibration_failures(replace(target, entries=10500), target)
    assert any(
        error.startswith("entries:") for error in sweep.calibration_failures(replace(target, entries=10510), target)
    )


@pytest.mark.parametrize(
    "damage",
    [
        "missing overrides",
        "missing profile",
        "missing overlap",
        "wrong overrides",
        "wrong profile",
        "bad overlap",
        "unknown band",
        "nonfinite overlap",
    ],
)
def test_missing_or_wrong_provenance_never_completes(
    sweep: ModuleType, target: synth.Stats, tmp_path: Path, damage: str
):
    data = row("denser", 0, target)
    match damage:
        case "missing overrides":
            del data["overrides"]
        case "missing profile":
            del data["profile"]
        case "missing overlap":
            del data["input_overlap_by_band"]
        case "wrong overrides":
            data["overrides"] = {}
        case "wrong profile":
            data["profile"]["back"] = 0.0
        case "bad overlap":
            data["input_overlap_by_band"]["2-4"]["overlap"] = -0.5
        case "unknown band":
            data["input_overlap_by_band"] = {"invented": {"overlap": 0.5, "pairs_share": 0.5}}
        case "nonfinite overlap":
            data["input_overlap_by_band"]["2-4"]["overlap"] = float("nan")
    report = sweep.run_sweep(["denser"], [0], lambda _c, _s: data, target, tmp_path / "report.json")
    assert report["complete"] is False
    assert report["passed"] is False
    assert "error" in report["results"][0]


def test_empty_overlap_is_missing_measurement_when_inputs_exist(sweep: ModuleType, target: synth.Stats, tmp_path: Path):
    data = row("baseline", 0, target)
    data["input_overlap_by_band"] = {}
    report = sweep.run_sweep(["baseline"], [0], lambda _c, _s: data, target, tmp_path / "report.json")
    assert report["complete"] is False
    assert report["passed"] is False
    assert "input overlap is missing" in report["results"][0]["error"]
