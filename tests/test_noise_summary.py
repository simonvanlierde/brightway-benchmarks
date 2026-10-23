"""scripts/noise_summary.py on a hand-written asv result file."""

import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "noise_summary.py"


def test_spread_per_case_and_parameter(tmp_path: Path):
    spec = importlib.util.spec_from_file_location("noise_summary", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    result = {
        "env_name": "env-a",
        "result_columns": ["result", "params", "samples"],
        "results": {
            "bench_lca.SingleScore.time_first_score": [
                [1.0, 2.0],
                [["'smoke'"], ["'LCA'", "'IterativeLCA'"]],
                [[1.0, 1.1, 0.9, 1.0], [2.0, 2.0, 2.0, 4.0]],
            ],
            "bench_lca.SingleScore.track_relative_error": [[0.0], [], [[0.0]]],
            "bench_import.timeraw_import_bw2data": [[0.05], [], [[0.05, 0.051]]],
            # Skipped at every parameter: asv drops the trailing empty samples column.
            "bench_lca.MonteCarlo.time_iterations": [[float("nan")], [["'smoke'"]]],
        },
    }
    (tmp_path / "abc-env-a.json").write_text(json.dumps(result))
    (tmp_path / "machine.json").write_text("{}")
    # A run without --append-samples has no samples column, and adds no rows.
    (tmp_path / "def-env-b.json").write_text(
        json.dumps({"result_columns": ["result", "params"], "results": result["results"]})
    )
    rows = module.rows(tmp_path)
    assert [r[0] for r in rows] == [
        "bench_lca.SingleScore.time_first_score('smoke', 'LCA')",
        "bench_lca.SingleScore.time_first_score('smoke', 'IterativeLCA')",
        "bench_import.timeraw_import_bw2data",
    ]
    _case, env, n, median, iqr, spread = rows[1]
    assert (env, n, median, spread) == ("env-a", 4, 2.0, 2.0)
    assert iqr == pytest.approx(0.25)


def test_preempted_samples_are_counted(tmp_path: Path):
    spec = importlib.util.spec_from_file_location("noise_summary", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    case = {"case": "bench_lca.SingleScore.time_first_score", "params": "'smoke', 'LCA'", "env": "env-a"}
    samples = [
        {"wall": 1.0, "cpu": 0.99, "nivcsw": 2},
        {"wall": 1.15, "cpu": 1.0, "nivcsw": 300},  # waited 13% of its time for the core
        {"wall": 2.0, "cpu": 1.98, "nivcsw": 4},
    ]
    (tmp_path / "rounds.jsonl").write_text("".join(json.dumps(case | s) + "\n" for s in samples))
    ((name, env, n, low, most, preempted),) = module.usage_rows(tmp_path / "rounds.jsonl")
    assert (name, env, n, preempted) == ("bench_lca.SingleScore.time_first_score('smoke', 'LCA')", "env-a", 3, 1)
    assert low == pytest.approx(1.0 / 1.15)
    assert most == pytest.approx(300 / 1.15)
