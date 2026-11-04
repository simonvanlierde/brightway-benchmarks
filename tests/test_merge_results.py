"""scripts/merge_results.py's merge of two asv result files."""

import importlib.util
import json
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "merge_results.py"
spec = importlib.util.spec_from_file_location("merge_results", SCRIPT)
assert spec is not None
assert spec.loader is not None
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
merge = module.merge

COLUMNS = ["result", "params", "version", "started_at", "duration", "stats_q_25"]


def result(row: list) -> str:
    return json.dumps({"result_columns": COLUMNS, "results": {"b": row}, "durations": {}})


def merged_row(old: list, new: list) -> list:
    return json.loads(merge(result(old), result(new)))["results"]["b"]


def test_cells_merge_across_two_axes_in_asvs_order():
    old = [[1, 2, 3, 4], [["'s'", "'e'"], ["'A'", "'B'"]], "v", 10, 5, [0.1, 0.2, 0.3, 0.4]]
    new = [[7, 8], [["'u'"], ["'A'", "'B'"]], "v", 20, 1, [0.7, 0.8]]
    assert merged_row(old, new) == [
        [7, 8, 1, 2, 3, 4],
        [["'u'", "'s'", "'e'"], ["'A'", "'B'"]],
        "v",
        20,
        1,
        [0.7, 0.8, 0.1, 0.2, 0.3, 0.4],
    ]


def test_a_new_failure_replaces_the_old_time():
    old = [[1, 2], [["'s'", "'e'"]], "v"]
    new = [[None], [["'s'"]], "v"]
    assert merged_row(old, new)[0] == [None, 2]


def test_a_changed_benchmark_keeps_only_the_new_cells():
    new = [[7], [["'u'"]], "v2"]
    assert merged_row([[1], [["'s'"]], "v1"], new) == new


def test_files_that_are_not_results_pass_through():
    assert merge('{"machine": "m"}', '{"machine": "n"}') == '{"machine": "n"}'
