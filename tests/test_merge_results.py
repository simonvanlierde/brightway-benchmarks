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


def test_a_benchmark_only_in_the_old_file_stays():
    old = {"result_columns": COLUMNS, "results": {"a": [[1], [["'s'"]], "v"], "b": [[2], [["'s'"]], "v"]}}
    new = {"result_columns": COLUMNS, "results": {"a": [[3], [["'u'"]], "v"]}}
    assert json.loads(merge(json.dumps(old), json.dumps(new)))["results"] == {
        "a": [[3, 1], [["'u'", "'s'"]], "v"],
        "b": [[2], [["'s'"]], "v"],
    }


def test_durations_keep_old_keys_and_take_new_values():
    old = {"result_columns": COLUMNS, "results": {"b": [[1], [["'s'"]], "v"]}, "durations": {"b": 1, "c": 2}}
    new = {"result_columns": COLUMNS, "results": {"b": [[3], [["'u'"]], "v"]}, "durations": {"b": 3}}
    assert json.loads(merge(json.dumps(old), json.dumps(new)))["durations"] == {"b": 3, "c": 2}


def test_a_different_number_of_axes_keeps_the_new_row():
    new = [[7], [["'u'"]], "v"]
    assert merged_row([[1, 2], [["'s'"], ["'A'", "'B'"]], "v"], new) == new


def test_an_old_row_without_params_keeps_the_new_row():
    new = [[7], [["'u'"]], "v"]
    assert merged_row([], new) == new


def test_other_result_columns_keep_the_new_text():
    old = json.dumps({"result_columns": [*COLUMNS, "samples"], "results": {"b": [[1], [["'s'"]], "v"]}})
    new = result([[7], [["'u'"]], "v"])
    assert merge(old, new) == new


def test_trailing_empty_columns_are_left_out():
    assert merged_row([[1], [["'s'"]], "v"], [[2], [["'u'"]], "v"]) == [[2, 1], [["'u'", "'s'"]], "v"]


def custom_row(columns: list[str], old: list, new: list) -> list:
    def text(row: list) -> str:
        return json.dumps({"result_columns": columns, "results": {"b": row}})

    return json.loads(merge(text(old), text(new)))["results"]["b"]


def test_a_cell_column_empty_in_both_stays_empty():
    columns = ["result", "params", "version", "stats_q_25", "started_at"]
    old, new = [[1], [["'s'"]], "v", None, 10], [[2], [["'u'"]], "v", None, 20]
    assert custom_row(columns, old, new) == [[2, 1], [["'u'", "'s'"]], "v", None, 20]


def test_samples_merge_per_cell():
    columns = ["result", "params", "version", "samples"]
    old, new = [[1], [["'s'"]], "v", [[1.0, 1.1]]], [[2], [["'u'"]], "v", [[2.0]]]
    assert custom_row(columns, old, new) == [[2, 1], [["'u'", "'s'"]], "v", [[2.0], [1.0, 1.1]]]
