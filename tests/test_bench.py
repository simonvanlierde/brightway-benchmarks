import ast
import itertools
import json
import os
import subprocess
import sys
import time
import types
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import numpy as np
import pytest

import bwbench
from bwbench import asv, synth
from bwbench import pytest as bw_pytest
from bwbench.bench import UNCHECKED, NotApplicable, bench, free_pardiso


def module(**namespace: object) -> types.ModuleType:
    mod = types.ModuleType("fake_bench")
    vars(mod).update(namespace)
    sys.modules[mod.__name__] = mod
    return mod


@bench({"size": ["smoke"], "n": [1, 2]}, rtol=1e-9, error="relative_error", asv="Doubling", timeout=60)
def double(size: str, n: int):
    return lambda: 2 * n, 2 * n


def setup(obj: object, method: str, *args: object) -> None:
    """Do what asv does before a method: every ``setup`` it finds on the class, then on the method."""
    assert not hasattr(obj, "setup"), "a class setup would run before every method, track_ included"
    getattr(getattr(obj, method), "setup")(*args)  # noqa: B009


def test_run_once_per_setup_and_check():
    prepared = double.prepare(size="smoke", n=3)
    assert prepared() == 6
    assert prepared.verify(6) == 0
    with pytest.raises(RuntimeError, match="twice"):
        prepared()
    with pytest.raises(AssertionError, match="relative error"):
        prepared.verify(7)


def test_expect_forms():
    @bench()
    def unchecked():
        return lambda: 1, UNCHECKED

    @bench()
    def checked_by_function():
        return lambda: 1, lambda result: 0.5 if result == 1 else 1 / 0

    @bench()
    def value_without_rtol():
        return lambda: 1, 1

    assert unchecked.prepare().verify(1) is None
    assert checked_by_function.prepare().verify(1) == 0.5
    with pytest.raises(ValueError, match="rtol"):
        value_without_rtol.prepare().verify(1)


def test_yield_teardown_runs_once_after_the_check():
    log = []

    @bench()
    def with_teardown():
        log.append("setup")
        yield lambda: log.append("run"), UNCHECKED
        log.append("teardown")

    prepared = with_teardown.prepare()
    prepared()
    prepared.teardown()
    prepared.teardown()
    assert log == ["setup", "run", "teardown"]


def test_asv_class_keeps_names_and_hides_runner_details():
    mod = module(double=double)
    (cls,) = asv.classes(mod.__name__)
    assert mod.Doubling is cls
    assert cls.__module__ == "fake_bench"
    assert cls.param_names == ["size", "n"]
    assert cls.number == 1
    assert cls.warmup_time == 0
    assert cls.timeout == 60
    assert cls.version == synth.profile_version()
    obj = cls()
    setup(obj, "time_double", "smoke", 2)
    obj.time_double("smoke", 2)
    obj.teardown("smoke", 2)
    setup(obj, "track_relative_error", "smoke", 2)
    assert obj.track_relative_error("smoke", 2) == 0


def test_asv_teardown_fails_a_wrong_result():
    @bench({"x": [1]}, rtol=1e-9)
    def wrong(x: int):
        return lambda: 2, 1

    (cls,) = asv.classes(module(wrong=wrong).__name__)
    obj = cls()
    setup(obj, "time_wrong", 1)
    obj.time_wrong(1)
    with pytest.raises(AssertionError):
        obj.teardown(1)


def test_first_time_is_once_per_key():
    assert bwbench.first_time("a", 1)
    assert not bwbench.first_time("a", 1)
    assert bwbench.first_time("a", 2)


def test_asv_checks_once_per_parameter_set():
    checked = []

    @bench({"x": [1, 2]})
    def counted(x: int):
        return lambda: x, lambda result: checked.append(result) or 0.0

    (cls,) = asv.classes(module(counted=counted).__name__)
    obj = cls()
    for x in (1, 1, 2):  # asv sets up and tears down around every sample
        setup(obj, "time_counted", x)
        obj.time_counted(x)
        obj.teardown(x)
    assert checked == [1, 2]


def test_asv_rounds_follow_bwbench_rounds(monkeypatch: pytest.MonkeyPatch):
    (default,) = asv.classes(module(double=double).__name__)
    monkeypatch.setenv("BWBENCH_ROUNDS", "1")
    (one,) = asv.classes(module(double=double).__name__)
    assert (vars(default)["rounds"], vars(one)["rounds"]) == (2, 1)


def test_asv_merges_benches_that_share_a_class():
    @bench({"x": [1]}, asv="Pair")
    def first(x: int):
        return lambda: x, UNCHECKED

    @bench({"x": [1]}, asv="Pair")
    def second(x: int):
        return lambda: x, UNCHECKED

    (cls,) = asv.classes(module(first=first, second=second).__name__)
    assert {"time_first", "time_second"} <= set(vars(cls))

    @bench({"y": [1]}, asv="Pair")
    def other(y: int):
        return lambda: y, UNCHECKED

    with pytest.raises(ValueError, match="same params"):
        asv.classes(module(first=first, other=other).__name__)


def test_pytest_adapter_parametrizes_and_marks():
    namespace: dict[str, Any] = {"double": double}
    bw_pytest.tests(namespace)
    test = namespace["test_double"]
    marks = {m.name for m in test.pytestmark}
    assert marks == {"parametrize", "benchmark"}

    class FakeBenchmark:
        def pedantic(self, target, setup, rounds, iterations):  # noqa: ANN001, ARG002
            setup()
            target()

    test(FakeBenchmark(), size="smoke", n=2)


def test_pytest_adapter_tears_down_the_warmup_setup():
    log = []

    @bench()
    def with_teardown():
        log.append("setup")
        yield lambda: log.append("run"), UNCHECKED
        log.append("teardown")

    namespace: dict[str, Any] = {"with_teardown": with_teardown}
    bw_pytest.tests(namespace)

    class WarmupBenchmark:  # pytest-codspeed's simulation: one warm-up round, then the measured one
        def pedantic(self, target, setup, rounds, iterations):  # noqa: ANN001, ARG002
            setup()
            target()
            setup()
            target()

    namespace["test_with_teardown"](WarmupBenchmark())
    assert log == ["setup", "run", "teardown", "setup", "run", "teardown"]


@pytest.mark.parametrize(("strict", "outcome"), [("", pytest.skip.Exception), ("1", NotImplementedError)])
def test_pytest_adapter_fails_unsupported_cases_when_strict(
    monkeypatch: pytest.MonkeyPatch, strict: str, outcome: type[BaseException]
):
    @bench()
    def unsupported():
        message = "bw2calc has no such class"
        raise NotImplementedError(message)

    namespace: dict[str, Any] = {"unsupported": unsupported}
    bw_pytest.tests(namespace)

    class OnceBenchmark:
        def pedantic(self, target, setup, rounds, iterations):  # noqa: ANN001, ARG002
            setup()
            target()

    monkeypatch.setenv("BWBENCH_STRICT", strict)
    # BaseException: pytest.skip's exception is not an Exception.
    with pytest.raises(BaseException, match="no such class") as raised:
        namespace["test_unsupported"](OnceBenchmark())
    assert raised.type is outcome


def test_pytest_adapter_skips_cases_for_another_solver_even_when_strict(monkeypatch: pytest.MonkeyPatch):
    @bench()
    def umfpack_only():
        message = "needs UMFPACK"
        raise NotApplicable(message)

    namespace: dict[str, Any] = {"umfpack_only": umfpack_only}
    bw_pytest.tests(namespace)

    class OnceBenchmark:
        def pedantic(self, target, setup, rounds, iterations):  # noqa: ANN001, ARG002
            setup()
            target()

    monkeypatch.setenv("BWBENCH_STRICT", "1")
    with pytest.raises(pytest.skip.Exception, match="needs UMFPACK"):
        namespace["test_umfpack_only"](OnceBenchmark())


def test_numpy_before_bwbench_warns():
    code = "import numpy, bwbench"
    unpinned = {k: v for k, v in os.environ.items() if k not in bwbench.PINNED}
    run = subprocess.run(
        [sys.executable, "-W", "error::RuntimeWarning", "-c", code], check=False, capture_output=True, env=unpinned
    )
    assert b"numpy was imported before bwbench" in run.stderr
    clean = subprocess.run([sys.executable, "-W", "error", "-c", "import bwbench, numpy"], check=False)
    assert clean.returncode == 0
    # Already pinned in the environment, as in-box.sh does for asv: numpy first is fine then.
    pinned = {**os.environ, "BWBENCH_THREADS": "1"} | dict.fromkeys(bwbench.PINNED, "1")
    late = subprocess.run([sys.executable, "-W", "error", "-c", code], check=False, env=pinned)
    assert late.returncode == 0


def test_no_benchmark_module_has_a_name_asv_takes_for_setup():
    # asv looks up setup and teardown in the module too, ignoring case.

    reserved = {"setup", "teardown", "setup_cache"}
    for path in (Path(__file__).resolve().parents[1] / "benchmarks").rglob("*.py"):
        tree = ast.parse(path.read_text())
        names = {a.asname or a.name for n in tree.body if isinstance(n, ast.ImportFrom | ast.Import) for a in n.names}
        names |= {n.name for n in tree.body if isinstance(n, ast.FunctionDef | ast.ClassDef)}
        names |= {t.id for n in tree.body if isinstance(n, ast.Assign) for t in n.targets if isinstance(t, ast.Name)}
        assert not {n for n in names if n.lower() in reserved}, path


def test_asv_track_and_teardown_paths():
    log = []

    @bench({"x": [1]}, rtol=1e-9, track={"double": lambda r: 2.0 * r})
    def counted(x: int):
        yield (lambda: x), 99  # a wrong result: the check fails in teardown
        log.append("teardown")

    (cls,) = asv.classes(module(counted=counted).__name__)
    cls().teardown(1)  # after a setup that never ran: nothing to check or tear down
    obj = cls()
    setup(obj, "track_double", 1)
    assert obj.track_double(1) == 2.0  # no record: it prepares and runs the case itself
    obj.teardown(1)
    assert log == ["teardown"]
    setup(obj, "time_counted", 1)
    obj.time_counted(1)
    with pytest.raises(AssertionError):
        obj.teardown(1)
    assert log == ["teardown", "teardown"]


def test_asv_refuses_two_benches_defining_one_method():
    @bench({"x": [1]}, asv="Same", error="relative_error")
    def first(x: int):
        return lambda: x, UNCHECKED

    @bench({"x": [1]}, asv="Same", error="relative_error")
    def second(x: int):
        return lambda: x, UNCHECKED

    with pytest.raises(ValueError, match="track_relative_error"):
        asv.classes(module(first=first, second=second).__name__)


class FakeBenchmark:
    def pedantic(self, target, setup, rounds, iterations):  # noqa: ANN001, ARG002
        setup()
        target()


def test_pytest_adapter_skips_and_still_tears_down():
    log = []

    @bench()
    def unsupported():
        log.append("setup")
        msg = "no such release"
        raise NotImplementedError(msg)
        yield  # a yield setup

    @bench()
    def crashing():
        def run() -> None:
            msg = "boom"
            raise RuntimeError(msg)

        yield run, UNCHECKED
        log.append("teardown")

    namespace: dict[str, Any] = {"unsupported": unsupported, "crashing": crashing}
    bw_pytest.tests(namespace)
    with pytest.raises(pytest.skip.Exception, match="no such release"):
        namespace["test_unsupported"](FakeBenchmark())
    with pytest.raises(RuntimeError, match="boom"):
        namespace["test_crashing"](FakeBenchmark())
    assert log == ["setup", "teardown"]


def test_pytest_adapter_tears_down_after_a_skip_in_run():
    log = []

    @bench()
    def late_skip():
        def run() -> None:
            msg = "found out while running"
            raise NotImplementedError(msg)

        yield run, UNCHECKED
        log.append("teardown")

    namespace: dict[str, Any] = {"late_skip": late_skip}
    bw_pytest.tests(namespace)
    with pytest.raises(pytest.skip.Exception, match="while running"):
        namespace["test_late_skip"](FakeBenchmark())
    assert log == ["teardown"]


def test_asv_peakmem_method_only_when_asked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    log = tmp_path / "rounds.jsonl"
    monkeypatch.setenv("BWBENCH_ROUNDLOG", str(log))

    @bench({"size": ["smoke"]}, asv="Memory", peakmem=True)
    def with_mem(size: str):
        return lambda: 1, UNCHECKED

    @bench({"size": ["smoke"]}, asv="Plain")
    def without(size: str):
        return lambda: 1, UNCHECKED

    mem, plain = asv.classes(module(with_mem=with_mem, without=without).__name__)
    assert hasattr(mem, "peakmem_with_mem")
    assert not hasattr(plain, "peakmem_without")
    obj = mem()
    setup(obj, "peakmem_with_mem", "smoke")
    obj.peakmem_with_mem("smoke")
    assert obj.state.results == {}  # asv reads the peak itself; there is nothing to check or log
    obj.teardown("smoke")
    assert not log.exists()  # a memory sample is not a timed sample


def test_asv_logs_cpu_and_wall_per_timed_sample(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    log = tmp_path / "noise" / "rounds.jsonl"
    monkeypatch.setenv("BWBENCH_ROUNDLOG", str(log))
    monkeypatch.setenv("ASV_ENV_NAME", "env-x")
    usage = itertools.chain([(10.0, 1.0, 5), (12.0, 2.5, 8)], itertools.repeat((0.0, 0.0, 0)))
    monkeypatch.setattr(asv, "_usage", lambda: next(usage))
    (cls,) = asv.classes(module(double=double).__name__)
    obj = cls()
    setup(obj, "time_double", "smoke", 2)
    obj.time_double("smoke", 2)
    obj.teardown("smoke", 2)
    setup(obj, "track_relative_error", "smoke", 2)
    obj.track_relative_error("smoke", 2)  # not a timed sample, so not logged
    obj.teardown("smoke", 2)
    (line,) = log.read_text().splitlines()
    entry = json.loads(line)
    assert entry["case"] == "fake_bench.Doubling.time_double"
    assert entry["params"] == "'smoke', 2"
    assert entry["env"] == "env-x"
    assert (entry["wall"], entry["cpu"], entry["nivcsw"]) == (2.0, 1.5, 3)
    assert "energy_j" not in entry  # BWBENCH_ENERGY is off


@pytest.fixture
def record_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[Path]:
    """A fresh home for the timed runs' records; the record file's path is cached per process."""
    monkeypatch.setenv("HOME", str(tmp_path))
    asv._record_file.cache_clear()  # noqa: SLF001
    yield tmp_path / ".bwbench-tracks"
    asv._record_file.cache_clear()  # noqa: SLF001


def test_track_methods_reuse_the_timed_run(monkeypatch: pytest.MonkeyPatch, record_file: Path):
    """In a box run, track_ methods read what the timed run's check recorded instead of running again."""
    monkeypatch.setenv("BWBENCH_COMMIT", "abc123")
    runs = []

    @bench({"x": [1, 2]}, rtol=1e-9, error="relative_error", track={"half": lambda r: np.float64(r) / 2})
    def counted(x: int):
        return (lambda: runs.append(x) or 2.0 * x), 2.0 * x

    (cls,) = asv.classes(module(counted=counted).__name__)
    obj = cls()
    setup(obj, "time_counted", 1)
    obj.time_counted(1)
    obj.teardown(1)
    setup(obj, "track_relative_error", 1)
    assert obj.track_relative_error(1) == 0
    setup(obj, "track_half", 1)
    assert obj.track_half(1) == 1.0
    assert runs == [1], "the track_ methods ran the case again"
    setup(obj, "track_half", 2)
    assert obj.track_half(2) == 2.0
    assert runs == [1, 2]
    (path,) = record_file.iterdir()
    path.write_text(path.read_text() + '{"case": "cut sho')  # a line a killed process left
    setup(obj, "track_half", 1)
    assert obj.track_half(1) == 1.0
    assert runs == [1, 2]


def test_a_failing_check_leaves_no_old_value(monkeypatch: pytest.MonkeyPatch, record_file: Path):
    """A timed run whose check raises makes track_ run the case and fail, even after an earlier pass."""
    monkeypatch.setenv("BWBENCH_COMMIT", "abc123")
    answer = [1.0]

    @bench({"x": [1]}, rtol=1e-9, error="relative_error")
    def flaky(x: int):
        return (lambda: answer[0]), 1.0

    (cls,) = asv.classes(module(flaky=flaky).__name__)
    obj = cls()
    setup(obj, "time_flaky", 1)
    obj.time_flaky(1)
    obj.teardown(1)
    answer[0] = 2.0
    bwbench._SEEN.clear()  # noqa: SLF001 - a new timed process
    setup(obj, "time_flaky", 1)
    obj.time_flaky(1)
    with pytest.raises(AssertionError):
        obj.teardown(1)
    setup(obj, "track_relative_error", 1)
    with pytest.raises(AssertionError):
        obj.track_relative_error(1)


def test_track_methods_run_the_case_outside_a_box_run(monkeypatch: pytest.MonkeyPatch, record_file: Path):
    monkeypatch.delenv("BWBENCH_COMMIT", raising=False)
    runs = []

    @bench({"x": [1]}, rtol=1e-9, error="relative_error")
    def counted(x: int):
        return (lambda: runs.append(x) or 1.0), 1.0

    (cls,) = asv.classes(module(counted=counted).__name__)
    obj = cls()
    setup(obj, "time_counted", 1)
    obj.time_counted(1)
    obj.teardown(1)
    setup(obj, "track_relative_error", 1)
    assert obj.track_relative_error(1) == 0
    assert runs == [1, 1]
    assert not record_file.exists()


def rapl(folder: Path, energy_uj: int) -> Path:
    """A stand-in for /sys/class/powercap/intel-rapl:0, whose counter wraps past 262143328850 µJ."""
    folder.mkdir(exist_ok=True)
    # Swap the file in whole: the meter thread reads it meanwhile, and write_text truncates first,
    # so a read in between sees "" and voids the sample, which sysfs never does.
    (folder / "energy_uj.tmp").write_text(f"{energy_uj}\n")
    (folder / "energy_uj.tmp").replace(folder / "energy_uj")
    (folder / "max_energy_range_uj").write_text("262143328850\n")
    return folder


def test_asv_logs_package_energy_across_a_counter_wrap(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    log = tmp_path / "rounds.jsonl"
    monkeypatch.setenv("BWBENCH_ROUNDLOG", str(log))
    monkeypatch.setenv("BWBENCH_ENERGY", "1")
    monkeypatch.setenv("BWBENCH_RAPL", str(rapl(tmp_path / "rapl", 262_142_328_850)))
    (cls,) = asv.classes(module(double=double).__name__)
    obj = cls()
    setup(obj, "time_double", "smoke", 2)
    obj.time_double("smoke", 2)
    rapl(tmp_path / "rapl", 2_000_000)  # 1 J to the wrap, 2 J after it
    obj.teardown("smoke", 2)
    (line,) = log.read_text().splitlines()
    assert json.loads(line)["energy_j"] == pytest.approx(3.0)


def test_asv_logs_no_energy_and_warns_once_when_the_counter_is_unreadable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    log = tmp_path / "rounds.jsonl"
    monkeypatch.setenv("BWBENCH_ROUNDLOG", str(log))
    monkeypatch.setenv("BWBENCH_ENERGY", "1")
    monkeypatch.setenv("BWBENCH_RAPL", str(tmp_path / "missing"))
    monkeypatch.setattr(asv, "_energy_warned", False)
    (cls,) = asv.classes(module(double=double).__name__)
    for _ in range(2):
        obj = cls()
        setup(obj, "time_double", "smoke", 2)
        obj.time_double("smoke", 2)
        obj.teardown("smoke", 2)
    entries = [json.loads(line) for line in log.read_text().splitlines()]
    assert len(entries) == 2
    assert not any("energy_j" in e for e in entries)
    assert capsys.readouterr().err.count("no energy is logged") == 1


def test_asv_logs_package_energy_across_a_whole_counter_cycle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """300 kJ from 1000 J on a 262143.32885 J counter ends above the start: the endpoints alone show 37.9 kJ."""
    log = tmp_path / "rounds.jsonl"
    monkeypatch.setenv("BWBENCH_ROUNDLOG", str(log))
    monkeypatch.setenv("BWBENCH_ENERGY", "1")
    monkeypatch.setenv("BWBENCH_RAPL", str(rapl(tmp_path / "rapl", 1_000_000_000)))
    monkeypatch.setattr(asv, "_ENERGY_INTERVAL", 0.01, raising=False)

    def run(n: int) -> int:
        rapl(tmp_path / "rapl", 201_000_000_000)  # 200 kJ in, no wrap yet
        time.sleep(0.2)  # the meter reads the counter here
        rapl(tmp_path / "rapl", 38_856_671_150)  # 100 kJ more, across the wrap
        return 2 * n

    @bench({"size": ["smoke"], "n": [2]}, rtol=1e-9, error="relative_error", asv="Doubling", timeout=60)
    def double(size: str, n: int):
        return lambda: run(n), 2 * n

    (cls,) = asv.classes(module(double=double).__name__)
    obj = cls()
    setup(obj, "time_double", "smoke", 2)
    obj.time_double("smoke", 2)
    obj.teardown("smoke", 2)
    (line,) = log.read_text().splitlines()
    assert json.loads(line)["energy_j"] == pytest.approx(300_000.0)


@pytest.mark.parametrize(("gap", "joules"), [(59.0, 1.0), (61.0, None)])
def test_asv_logs_no_energy_when_the_counter_was_not_read_often_enough(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, gap: float, joules: float | None
):
    """A gap over 60 s between readings could hide whole counter cycles, so the sample gets no energy."""
    log = tmp_path / "rounds.jsonl"
    monkeypatch.setenv("BWBENCH_ROUNDLOG", str(log))
    monkeypatch.setenv("BWBENCH_ENERGY", "1")
    monkeypatch.setenv("BWBENCH_RAPL", str(rapl(tmp_path / "rapl", 1_000_000)))
    clock = itertools.chain([0.0], itertools.repeat(gap))  # every reading after the first comes gap s later
    monkeypatch.setattr(asv.time, "monotonic", lambda: next(clock))
    (cls,) = asv.classes(module(double=double).__name__)
    obj = cls()
    setup(obj, "time_double", "smoke", 2)
    obj.time_double("smoke", 2)
    rapl(tmp_path / "rapl", 2_000_000)
    obj.teardown("smoke", 2)
    (line,) = log.read_text().splitlines()
    assert json.loads(line).get("energy_j") == joules


def test_asv_logs_no_energy_when_a_later_counter_read_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    log = tmp_path / "rounds.jsonl"
    monkeypatch.setenv("BWBENCH_ROUNDLOG", str(log))
    monkeypatch.setenv("BWBENCH_ENERGY", "1")
    monkeypatch.setenv("BWBENCH_RAPL", str(rapl(tmp_path / "rapl", 1_000_000)))
    (cls,) = asv.classes(module(double=double).__name__)
    obj = cls()
    setup(obj, "time_double", "smoke", 2)
    obj.time_double("smoke", 2)
    (tmp_path / "rapl" / "energy_uj").write_text("garbled\n")
    obj.teardown("smoke", 2)  # a sample without energy, not a failed benchmark
    (line,) = log.read_text().splitlines()
    assert "energy_j" not in json.loads(line)


def test_only_timed_methods_set_up():
    """Only time_ and peakmem_ prepare; a class setup would run before every method, track_ included."""
    prepared = []

    @bench({"x": [1]}, asv="Pair", peakmem=True, error="relative_error", rtol=1e-9)
    def first(x: int):
        prepared.append("first")
        return lambda: x, x

    @bench({"x": [1]}, asv="Pair")
    def second(x: int):
        prepared.append("second")
        return lambda: x, UNCHECKED

    (cls,) = asv.classes(module(first=first, second=second).__name__)
    assert "setup" not in vars(cls)
    assert hasattr(vars(cls)["track_relative_error"], "setup")
    obj = cls()
    setup(obj, "track_relative_error", 1)
    assert prepared == ["first"]  # no record: the track_ method prepares its case in setup
    obj.teardown(1)
    for method, expected in [("time_first", "first"), ("peakmem_first", "first"), ("time_second", "second")]:
        prepared.clear()
        setup(obj, method, 1)
        assert prepared == [expected]  # not the other bench of the class
        getattr(obj, method)(1)
        obj.teardown(1)


def test_a_skipped_case_skips_its_track_methods(monkeypatch: pytest.MonkeyPatch, record_file: Path):
    """Only a setup may raise the NotImplementedError that asv reads as a skip, track_ methods included."""
    monkeypatch.setenv("BWBENCH_COMMIT", "abc123")

    @bench({"x": [1, 2]}, rtol=1e-9, error="relative_error", track={"half": lambda r: r / 2})
    def skipped(x: int):
        if x == 2:
            raise NotApplicable
        return (lambda: 1.0), 1.0

    (cls,) = asv.classes(module(skipped=skipped).__name__)
    obj = cls()
    for method in ("time_skipped", "track_relative_error", "track_half"):
        with pytest.raises(NotImplementedError):
            setup(obj, method, 2)


def test_a_recorded_track_value_prepares_nothing(monkeypatch: pytest.MonkeyPatch, record_file: Path):
    monkeypatch.setenv("BWBENCH_COMMIT", "abc123")
    prepared = []

    @bench({"x": [1]}, rtol=1e-9, error="relative_error")
    def counted(x: int):
        prepared.append(x)
        return (lambda: 1.0), 1.0

    (cls,) = asv.classes(module(counted=counted).__name__)
    obj = cls()
    setup(obj, "time_counted", 1)
    obj.time_counted(1)
    obj.teardown(1)
    prepared.clear()
    setup(obj, "track_relative_error", 1)
    assert obj.track_relative_error(1) == 0
    assert prepared == []


def test_knob_strips_spaces_around_each_value(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("BWBENCH_SIZES", "smoke, ecoinvent")
    assert bwbench.knob("sizes", "smoke") == ["smoke", "ecoinvent"]


def test_free_pardiso_skips_a_hidden_pypardiso(monkeypatch: pytest.MonkeyPatch):
    # bwbench.timecase hides a solver with a None entry, which `in sys.modules` still finds.
    monkeypatch.setitem(sys.modules, "pypardiso", None)
    free_pardiso()
