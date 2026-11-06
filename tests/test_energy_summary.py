"""scripts/energy_summary.py on a hand-written round log."""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "energy_summary.py"


def write_log(path: Path) -> None:
    lca = {"case": "bench_lca.SingleScore.time_first_score", "env": "env-a"}
    samples = [
        lca | {"params": "'smoke', 'umfpack'", "wall": 1.0, "energy_j": 30.0},
        lca | {"params": "'smoke', 'umfpack'", "wall": 2.0, "energy_j": 50.0},
        lca | {"params": "'smoke', 'umfpack'", "wall": 1.0, "energy_j": 40.0},
        lca | {"params": "'smoke', 'superlu'", "wall": 4.0, "energy_j": 100.0},
        lca | {"params": "'smoke', 'superlu'", "wall": 4.0},  # logged without energy: left out
        {"case": "bench_import.time_import", "params": "", "env": "env-a", "wall": 1.0},  # no energy at all
    ]
    path.write_text("".join(json.dumps(s | {"cpu": s["wall"], "nivcsw": 0}) + "\n" for s in samples))


def test_median_joules_above_idle_and_watts_per_case(tmp_path: Path):
    spec = importlib.util.spec_from_file_location("energy_summary", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    write_log(tmp_path / "rounds.jsonl")
    rows = module.rows(tmp_path / "rounds.jsonl", idle_w=10.0)
    assert [r[:3] for r in rows] == [
        ("bench_lca.SingleScore.time_first_score('smoke', 'superlu')", "env-a", 1),
        ("bench_lca.SingleScore.time_first_score('smoke', 'umfpack')", "env-a", 3),
    ]
    _case, _env, _n, joules, above, watts = rows[1]
    assert joules == 40.0
    assert above == 30.0  # 20, 30, 30 J above 10 W of idle
    assert watts == pytest.approx(30.0)  # 30, 25, 40 W


def test_prints_a_markdown_table_without_an_idle_baseline(tmp_path: Path):
    write_log(tmp_path / "rounds.jsonl")
    out = subprocess.run(
        [sys.executable, str(SCRIPT), str(tmp_path / "rounds.jsonl")], capture_output=True, text=True, check=True
    ).stdout.splitlines()
    assert out[0].startswith("| case | environment | samples | median J |")
    assert out[2] == "| bench_lca.SingleScore.time_first_score('smoke', 'superlu') | env-a | 1 | 100 | - | 25 |"
