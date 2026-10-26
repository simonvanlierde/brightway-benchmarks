"""scripts/release_report.py: counting one asv result file."""

import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "release_report.py"


def load():
    spec = importlib.util.spec_from_file_location("release_report", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_tally_counts_ok_failed_and_skipped():
    result = {
        "commit_hash": "0123456789abcdef",
        "env_name": "env-a",
        "results": {
            "bench_lca.A.time_x": [[1.0, None, float("nan")]],
            "bench_lca.B.time_y": [None],
            "bench_lca.C.time_z": [0.5],
        },
    }
    assert load().tally(json.dumps(result)) == ("01234567", "env-a", 2, 2, 1, ["A.time_x", "B.time_y"])


@pytest.mark.parametrize("text", ["", "{", "[]", '{"results": {"a.b": []}}', '{"results": {"nodot": [null]}}'])
def test_tally_rejects_malformed_input(text: str):
    with pytest.raises((ValueError, AttributeError, IndexError, KeyError, TypeError)):
        load().tally(text)
