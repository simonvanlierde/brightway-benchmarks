import ast
import os
import subprocess
import sys
import types
from pathlib import Path
from typing import Any

import pytest

import bwbench
from bwbench import asv, synth
from bwbench import pytest as bw_pytest
from bwbench.bench import UNCHECKED, bench


def module(**namespace: object) -> types.ModuleType:
    mod = types.ModuleType("fake_bench")
    vars(mod).update(namespace)
    sys.modules[mod.__name__] = mod
    return mod


@bench({"size": ["smoke"], "n": [1, 2]}, rtol=1e-9, error="relative_error", asv="Doubling", timeout=60)
def double(size: str, n: int):
    return lambda: 2 * n, 2 * n


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
    assert cls.version == synth.profile_version(["smoke"])
    obj = cls()
    obj.setup("smoke", 2)
    obj.time_double("smoke", 2)
    obj.teardown("smoke", 2)
    obj.setup("smoke", 2)
    assert obj.track_relative_error("smoke", 2) == 0


def test_asv_teardown_fails_a_wrong_result():
    @bench({"x": [1]}, rtol=1e-9)
    def wrong(x: int):
        return lambda: 2, 1

    (cls,) = asv.classes(module(wrong=wrong).__name__)
    obj = cls()
    obj.setup(1)
    obj.time_wrong(1)
    with pytest.raises(AssertionError):
        obj.teardown(1)


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
