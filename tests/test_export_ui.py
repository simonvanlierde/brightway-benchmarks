"""scripts/export_ui.py on hand-written asv result files, checked against ui/schema/."""

import hashlib
import importlib
import json
import math
import re
import shutil
import subprocess
from pathlib import Path
from types import ModuleType

import pytest
from jsonschema import Draft202012Validator, ValidationError

GIT = shutil.which("git") or "git"
ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "ui" / "schema"
STACK = "-BWBENCH_STACKaaaa1111"
PARAMS = [["'ecoinvent'"], ["'LCA'", "'IterativeLCA'"]]
NAMES = ["size", "cls"]
KINDS = {  # asv's benchmark type, as in benchmarks.json
    "bench_lca.SingleScore.time_first_score": "time",
    "bench_lca.SingleScore.peakmem_first_score": "peakmemory",
    "bench_lca.SingleScore.track_relative_error": "track",
}
INFO = {k: {"type": t, "param_names": NAMES} for k, t in KINDS.items()}
COLUMNS = ["result", "params", "version", "started_at", "duration", "stats_ci_99_a", "stats_ci_99_b"]
TIME = "bench_lca.SingleScore.time_first_score"


def result(commit: str, env: str, date: int, first: list, ci: tuple[list, list]) -> dict:
    """An asv result file with a time case (with its 99% interval), peak memory and a track case."""
    res = {
        TIME: [first, PARAMS, "v", 0, 1.0, *ci],
        "bench_lca.SingleScore.peakmem_first_score": [[5e8, 6e8], PARAMS],
        "bench_lca.SingleScore.track_relative_error": [[1e-15, 1e-15], PARAMS],
    }
    return {"commit_hash": commit, "env_name": env, "date": date, "result_columns": COLUMNS, "results": res}


def schema(name: str) -> Draft202012Validator:
    """A validator for ui/schema/NAME.schema.json that checks formats such as date-time too."""
    return Draft202012Validator(
        json.loads((SCHEMA / f"{name}.schema.json").read_text()), format_checker=Draft202012Validator.FORMAT_CHECKER
    )


@pytest.fixture
def export_ui(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    # Imported by name, so that its own `from release_changes import STACK` resolves.
    return importlib.import_module("export_ui")


def layout(tmp_path: Path, files: dict[str, dict], stack: str = "", info: dict = INFO) -> Path:
    """results/s/MACHINE/NAME.json for each "MACHINE/NAME" in FILES, and asv/s.stack.txt."""
    (tmp_path / "results" / "s").mkdir(parents=True)
    (tmp_path / "results" / "s" / "benchmarks.json").write_text(json.dumps({"version": 2} | info))
    for where, data in files.items():
        path = tmp_path / "results" / "s" / f"{where}.json"
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps(data))
    (tmp_path / "asv").mkdir()
    if stack:
        (tmp_path / "asv" / "s.stack.txt").write_text(stack)
    return tmp_path / "results"


def run(
    export_ui: ModuleType, results: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[dict, dict[tuple[str, str], dict]]:
    """The index, and each report by (machine name, commit), after an export from RESULTS."""
    monkeypatch.chdir(results.parent)
    out = results.parent / "out"
    index = export_ui.export(results, out)
    assert json.loads((out / "index.json").read_text()) == index
    machines = {m["id"]: m["name"] for m in index["machines"]}
    return index, {
        (machines[r["machine"]], r["commit"]): json.loads((out / r["path"]).read_text()) for r in index["reports"]
    }


def value(index: dict, report: dict, params: list[str], env: str, measure: str = "latency") -> dict:
    """The metric for the time case at PARAMS in ENV, looked up through the index as the UI does."""
    envs = {e["id"]: e["name"] for e in index["environments"]}
    benchmarks = {b["id"]: b["name"] for b in index["benchmarks"]}
    (case,) = [
        c
        for c in index["cases"]
        if c["params"] == params and envs[c["environment"]] == env and benchmarks[c["benchmark"]] == TIME
    ]
    return report[case["id"]][measure]


def test_one_metric_per_case_parameters_and_environment(export_ui: ModuleType):
    data = result("ab" * 20, "uv-py3.12-umfpack" + STACK, 0, [9.05, None], ([9.0, None], [9.1, None]))
    out = export_ui.metrics(data, KINDS)
    # Seconds become latency in nanoseconds, with asv's 99% interval as the bounds.
    first = [m for n, p, _, m in out if n == TIME and p == ("'ecoinvent'", "'LCA'")]
    assert first == [{"value": pytest.approx(9.05e9), "lower_value": 9.0e9, "upper_value": pytest.approx(9.1e9)}]
    # A failed case (None) has no metric; peak memory is its own measure; track_ cases are left out.
    assert not [p for n, p, _, _ in out if n == TIME and p == ("'ecoinvent'", "'IterativeLCA'")]
    assert {(n.rsplit(".", 1)[1], measure) for n, _, measure, _ in out} == {
        ("time_first_score", "latency"),
        ("peakmem_first_score", "peak-memory"),
    }


def test_the_measure_comes_from_the_asv_type_not_the_name(export_ui: ModuleType):
    data = result("ab" * 20, "e", 0, [1.0, 2.0], ([1.0, 2.0], [1.0, 2.0]))
    data["results"]["bench_x.Odd.track_wall_time"] = [[3.0], [["1"]]]
    # A track_ name asv reports as a time still counts, and a time_ name of another type does not.
    kinds = KINDS | {"bench_x.Odd.track_wall_time": "time", TIME: "track"}
    measures = {(n, m) for n, _, m, _ in export_ui.metrics(data, kinds)}
    assert ("bench_x.Odd.track_wall_time", "latency") in measures
    assert not [n for n, _ in measures if n == TIME]


def test_a_skipped_case_and_a_case_without_parameters(export_ui: ModuleType):
    data = result("ab" * 20, "e", 0, [math.nan, 1.0], ([math.nan, 1.0], [math.nan, 1.0]))
    data["results"]["bench_import.timeraw_import_bw2calc"] = [0.5]
    out = export_ui.metrics(data, KINDS | {"bench_import.timeraw_import_bw2calc": "time"})
    assert not [p for n, p, _, _ in out if n == TIME and p == ("'ecoinvent'", "'LCA'")]  # NaN: skipped
    assert ("bench_import.timeraw_import_bw2calc", (), "latency", {"value": pytest.approx(5e8)}) in out


def test_bounds_are_read_per_parameter_set(export_ui: ModuleType):
    # The first parameter set has no interval, the second has one: its bounds are its own.
    data = result("ab" * 20, "e", 0, [1.0, 2.0], ([None, 1.9], [None, 2.1]))
    out = {p: m for n, p, _, m in export_ui.metrics(data, KINDS) if n == TIME}
    assert out[("'ecoinvent'", "'LCA'")] == {"value": 1e9}
    second = out[("'ecoinvent'", "'IterativeLCA'")]
    assert (second["lower_value"], second["upper_value"]) == pytest.approx((1.9e9, 2.1e9))


def test_one_report_per_machine_and_commit_oldest_first(
    export_ui: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    old, new = "11" * 20, "22" * 20
    files = {
        f"m/{c[:8]}-{env}": result(c, env + STACK, date, [1.0, 2.0], ([1.0, 2.0], [1.0, 2.0]))
        for c, date, env in [(new, 2_000_000, "a"), (old, 1_000_000, "a"), (old, 1_000_000, "b")]
    }
    files["n/22222222-a"] = result(new, "a" + STACK, 2_000_000, [3.0, 4.0], ([3.0, 4.0], [3.0, 4.0]))
    index, reports = run(export_ui, layout(tmp_path, files), monkeypatch)
    # Each machine folder is a machine of its own, so its results are never pooled with another's.
    assert sorted(reports) == [("m", old), ("m", new), ("n", new)]
    assert value(index, reports["m", new], ["'ecoinvent'", "'LCA'"], "a")["value"] == 1e9
    assert value(index, reports["n", new], ["'ecoinvent'", "'LCA'"], "a")["value"] == 3e9
    assert len(reports["m", old]) == 2 * 2 * 2  # both environments, both measures, both parameter sets
    # Commits oldest first; asv's date is in milliseconds.
    assert [(c["id"], c["date"]) for c in index["commits"]] == [
        (old, "1970-01-01T00:16:40Z"),
        (new, "1970-01-01T00:33:20Z"),
    ]


def test_one_stack_per_commit_and_environment(export_ui: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    commit = "44" * 20
    current = hashlib.sha256(b"numpy==2.5.3\n").hexdigest()[:8]
    files = {
        f"m/{commit[:8]}-{stack}": result(commit, f"a-BWBENCH_STACK{stack}", 0, [v, 1.0], ([v, 1.0], [v, 1.0]))
        for stack, v in [("00000000", 10.4), (current, 12.5), ("ffffffff", 15.4)]
    }
    # The current stack (asv/s.stack.txt) wins over the others, whatever order the files load in.
    index, reports = run(export_ui, layout(tmp_path, files, "numpy==2.5.3\n"), monkeypatch)
    assert value(index, reports["m", commit], ["'ecoinvent'", "'LCA'"], "a")["value"] == pytest.approx(12.5e9)
    # With no result on the current stack, the lowest stack hash wins.
    del files[f"m/{commit[:8]}-{current}"]
    index, reports = run(export_ui, layout(tmp_path / "x", files, "numpy==2.5.3\n"), monkeypatch)
    assert value(index, reports["m", commit], ["'ecoinvent'", "'LCA'"], "a")["value"] == pytest.approx(10.4e9)


def test_a_case_written_twice_is_refused(export_ui: ModuleType):
    data = result("ab" * 20, "e" + STACK, 0, [1.0, 2.0], ([1.0, 2.0], [1.0, 2.0]))
    with pytest.raises(SystemExit, match="twice in one report"):
        export_ui.Catalog().report("s", [data, data], INFO)


def test_ids_are_stable_slugs_unique_when_names_differ_only_at_the_end(export_ui: ModuleType):
    a = "bench_lca.MultiScores.time_scores('ecoinvent', 1, 'MultiLCA') [uv-py3.12-numpy2.5.3-scipy1.18.1]"
    b = a.replace("[uv-py3.12", "[uv-py3.13")
    assert export_ui.slug(a) != export_ui.slug(b)
    assert len(export_ui.slug(a)) <= 64
    assert export_ui.slug(a) == "bench-lca-multiscores-time-scores-ecoinvent-1-multi-122957eba918"  # links use it


def test_the_export_follows_the_schema(export_ui: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    files = {
        f"m/{c[:8]}-a": result(c, "a" + STACK, date, [1.0, None], ([0.9, None], [1.1, None]))
        for c, date in [("11" * 20, 1_000_000), ("22" * 20, 2_000_000)]
    }
    results = layout(tmp_path, files)
    (results.parent / "asv" / "s.hashes").write_text("1111111111111111111111111111111111111111\n")
    index, reports = run(export_ui, results, monkeypatch)
    schema("index").validate(index)
    check = schema("report")
    for report in reports.values():
        check.validate(report)
    # A release named by its commit, not a tag, is shown by its first 8 characters.
    assert [c.get("release") for c in index["commits"]] == ["11111111", None]
    # Every id a record names is one the index defines.
    ids = {k: {x["id"] for x in index[k]} for k in ("groups", "measures", "machines", "environments", "benchmarks")}
    assert {m for b in index["benchmarks"] for m in b["measures"]} <= ids["measures"]
    assert {c["benchmark"] for c in index["cases"]} == ids["benchmarks"]
    assert {c["environment"] for c in index["cases"]} == ids["environments"]
    assert {r["machine"] for r in index["reports"]} == ids["machines"]
    assert {r["group"] for r in index["reports"]} == ids["groups"]
    cases = {c["id"] for c in index["cases"]}
    assert all(report.keys() <= cases for report in reports.values())
    # Each metric is in a measure its benchmark lists, and its bounds hold its value.
    measures = {
        c["id"]: {*next(b for b in index["benchmarks"] if b["id"] == c["benchmark"])["measures"]}
        for c in index["cases"]
    }
    for report in reports.values():
        for case, metrics in report.items():
            assert metrics.keys() <= measures[case]
            for m in metrics.values():
                assert m.get("lower_value", m["value"]) <= m["value"] <= m.get("upper_value", m["value"])
    assert {m["id"]: (m["better"], m["statistic"]) for m in index["measures"]} == {
        "latency": ("lower", "median"),
        "peak-memory": ("lower", "max"),
    }
    # The axes hold the values that ran: IterativeLCA failed in every commit.
    assert index["benchmarks"][0]["params"] == [
        {"name": "size", "values": ["'ecoinvent'"], "labels": ["ecoinvent"]},
        {"name": "cls", "values": ["'LCA'"], "labels": ["LCA"]},
    ]


def test_the_ui_fixtures_follow_the_schema():
    # The UI's tests read these through its own validator; this one keeps both readings in step.
    data = ROOT / "ui" / "test" / "fixtures" / "data"
    index = json.loads((data / "index.json").read_text())
    schema("index").validate(index)
    check = schema("report")
    for report in index["reports"]:
        check.validate(json.loads((data / report["path"]).read_text()))


def test_a_parameter_count_mismatch_is_skipped_with_one_warning(
    export_ui: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    files = {
        f"m/{c[:8]}-a": result(c, "a" + STACK, date, [1.0, 2.0], ([1.0, 2.0], [1.0, 2.0]))
        for c, date in [("11" * 20, 1_000_000), ("22" * 20, 2_000_000)]
    }
    info = INFO | {TIME: {"type": "time", "param_names": ["size"]}}  # the results have two
    index, reports = run(export_ui, layout(tmp_path, files, info=info), monkeypatch)
    assert [b["name"] for b in index["benchmarks"]] == ["bench_lca.SingleScore.peakmem_first_score"]
    assert all(len(r) == 2 for r in reports.values())  # peak memory's two parameter sets
    warnings = capsys.readouterr().err.splitlines()
    assert warnings == [f"export_ui: s {TIME} has 2 parameters where benchmarks.json names 1; skipped"]


def test_a_nan_bound_is_left_out(export_ui: ModuleType):
    data = result("ab" * 20, "e", 0, [1.0, 2.0], ([math.nan, 1.9], [1.1, math.inf]))
    out = {p: m for n, p, _, m in export_ui.metrics(data, KINDS) if n == TIME}
    assert out == {("'ecoinvent'", "'LCA'"): {"value": 1e9}, ("'ecoinvent'", "'IterativeLCA'"): {"value": 2e9}}


def test_nan_is_never_written(export_ui: ModuleType, tmp_path: Path):
    # NaN is not JSON: the browser's parser would refuse the whole file.
    with pytest.raises(ValueError, match="not JSON compliant"):
        export_ui.write(tmp_path / "x.json", {"case": {"latency": {"value": math.nan}}})


def test_bounds_that_do_not_hold_the_value_are_left_out(export_ui: ModuleType):
    data = result("ab" * 20, "e", 0, [1.0, 2.0], ([1.1, 1.9], [1.2, 2.1]))  # 1.0 is below its interval
    out = {p: m for n, p, _, m in export_ui.metrics(data, KINDS) if n == TIME}
    assert out[("'ecoinvent'", "'LCA'")] == {"value": 1e9}
    assert out[("'ecoinvent'", "'IterativeLCA'")]["lower_value"] == pytest.approx(1.9e9)


def test_a_release_tag_resolves_through_the_mirror(
    export_ui: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    # asv's mirror: a bare repository with one commit, tagged 1.0. 2.0 is in the hashes file only.
    mirror = tmp_path / ".asv" / "s"
    git = [GIT, "--git-dir", str(mirror)]
    subprocess.run([GIT, "init", "-q", "--bare", str(mirror)], check=True)
    tree = subprocess.run([*git, "mktree"], input="", capture_output=True, text=True, check=True).stdout.strip()
    commit = subprocess.run(
        [*git, "-c", "user.name=t", "-c", "user.email=t@t.test", "commit-tree", tree, "-m", "1.0"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    subprocess.run([*git, "tag", "1.0", commit], check=True)
    files = {f"m/{commit[:8]}-a": result(commit, "a" + STACK, 1_000_000, [1.0, 2.0], ([1.0, 2.0], [1.0, 2.0]))}
    results = layout(tmp_path, files)
    (tmp_path / "asv" / "s.hashes").write_text("1.0\n2.0\n")
    index, _ = run(export_ui, results, monkeypatch)
    assert [(c["id"], c.get("release")) for c in index["commits"]] == [(commit, "1.0")]
    assert capsys.readouterr().err == "export_ui: .asv/s lacks 2.0; `just bench s` refreshes it\n"


def test_axes_follow_benchmarks_json_and_show_plain_values(
    export_ui: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    files = {f"m/{'11' * 4}-a": result("11" * 20, "a" + STACK, 0, [1.0, 2.0], ([1.0, 2.0], [1.0, 2.0]))}
    files["m/11111111-a"]["results"][TIME][1] = [["'ecoinvent'"], ["'LCA'", "'IterativeLCA'", "<lambda>"]]
    files["m/11111111-a"]["results"][TIME] = [[1.0, 2.0, 3.0], files["m/11111111-a"]["results"][TIME][1]]
    # benchmarks.json lists the axes in their own order, with a size that never ran here.
    params = [["'smoke'", "'ecoinvent'"], ["'IterativeLCA'", "'LCA'"]]
    info = INFO | {TIME: {"type": "time", "param_names": NAMES, "params": params}}
    index, _ = run(export_ui, layout(tmp_path, files, info=info), monkeypatch)
    (time,) = [b for b in index["benchmarks"] if b["name"] == TIME]
    assert time["params"] == [
        {"name": "size", "values": ["'ecoinvent'"], "labels": ["ecoinvent"]},
        # Listed values first, in benchmarks.json's order; then the rest as they came. Text that
        # is not a Python literal is shown as it is.
        {
            "name": "cls",
            "values": ["'IterativeLCA'", "'LCA'", "<lambda>"],
            "labels": ["IterativeLCA", "LCA", "<lambda>"],
        },
    ]
    assert {tuple(c["params"]) for c in index["cases"] if c["benchmark"] == time["id"]} == {
        ("'ecoinvent'", "'LCA'"),
        ("'ecoinvent'", "'IterativeLCA'"),
        ("'ecoinvent'", "<lambda>"),
    }


def test_a_name_without_letters_still_makes_an_id(export_ui: ModuleType):
    assert re.fullmatch(r"x-[0-9a-f]{12}", export_ui.slug("!!!"))


def test_parameter_values_with_commas_make_distinct_cases(export_ui: ModuleType):
    data = result("ab" * 20, "e", 0, [1.0, 2.0, 3.0, 4.0], ([1.0] * 4, [4.0] * 4))
    data["results"] = {TIME: [[1.0, 2.0, 3.0, 4.0], [["x, y", "x"], ["z", "y, z"]]]}
    # Joined with ", ", (x, y; z) and (x; y, z) would read the same.
    report = export_ui.Catalog().report("s", [data], INFO)
    assert len(report) == 4


def test_the_schema_checks_formats():
    index = json.loads((ROOT / "ui" / "test" / "fixtures" / "data" / "index.json").read_text())
    with pytest.raises(ValidationError, match="is not a 'date-time'"):
        schema("index").validate(index | {"generated_at": "yesterday"})
