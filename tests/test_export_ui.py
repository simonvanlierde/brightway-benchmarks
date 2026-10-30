"""scripts/export_ui.py on hand-written asv result files, checked against ui/schema/."""

import hashlib
import importlib
import json
import math
from pathlib import Path
from types import ModuleType

import pytest
from jsonschema import Draft202012Validator

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
    Draft202012Validator(json.loads((SCHEMA / "index.schema.json").read_text())).validate(index)
    check = Draft202012Validator(json.loads((SCHEMA / "report.schema.json").read_text()))
    for report in reports.values():
        check.validate(report)
    # A release named by its commit, not a tag, is shown by its first 8 characters.
    assert [c.get("release") for c in index["commits"]] == ["11111111", None]
    # Every id a record names is one the index defines.
    ids = {k: {x["id"] for x in index[k]} for k in ("groups", "measures", "machines", "environments", "benchmarks")}
    assert {b["measure"] for b in index["benchmarks"]} <= ids["measures"]
    assert {c["benchmark"] for c in index["cases"]} == ids["benchmarks"]
    assert {c["environment"] for c in index["cases"]} == ids["environments"]
    assert {r["machine"] for r in index["reports"]} == ids["machines"]
    assert {r["group"] for r in index["reports"]} == ids["groups"]
    cases = {c["id"] for c in index["cases"]}
    assert all(report.keys() <= cases for report in reports.values())
    # The axes hold the values that ran: IterativeLCA failed in every commit.
    assert index["benchmarks"][0]["params"] == [
        {"name": "size", "values": ["'ecoinvent'"]},
        {"name": "cls", "values": ["'LCA'"]},
    ]


def test_the_ui_fixtures_follow_the_schema():
    # The UI's tests read these through its own validator; this one keeps both readings in step.
    data = ROOT / "ui" / "test" / "fixtures" / "data"
    index = json.loads((data / "index.json").read_text())
    Draft202012Validator(json.loads((SCHEMA / "index.schema.json").read_text())).validate(index)
    check = Draft202012Validator(json.loads((SCHEMA / "report.schema.json").read_text()))
    for report in index["reports"]:
        check.validate(json.loads((data / report["path"]).read_text()))
