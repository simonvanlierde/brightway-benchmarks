import importlib.util
import sys
from contextlib import ExitStack
from pathlib import Path
from types import ModuleType
from typing import ClassVar

import numpy as np
import pytest
from hypothesis import given
from hypothesis import strategies as st
from scipy import sparse
from scipy.sparse.linalg import splu


@pytest.fixture
def script(monkeypatch: pytest.MonkeyPatch):
    path = Path(__file__).resolve().parents[1] / "scripts" / "solver_factorize.py"
    monkeypatch.syspath_prepend(str(path.parent))
    spec = importlib.util.spec_from_file_location("solver_factorize", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    return module


def test_imports_without_pymetis(monkeypatch: pytest.MonkeyPatch):
    # Its documented commands install no pymetis: measure_stats, which it imports, must not need it at import.
    monkeypatch.setitem(sys.modules, "pymetis", None)
    monkeypatch.delitem(sys.modules, "measure_stats", raising=False)
    path = Path(__file__).resolve().parents[1] / "scripts" / "solver_factorize.py"
    monkeypatch.syspath_prepend(str(path.parent))
    spec = importlib.util.spec_from_file_location("solver_factorize", path)
    assert spec is not None
    assert spec.loader is not None
    spec.loader.exec_module(importlib.util.module_from_spec(spec))


class CpuSolver:
    instances: ClassVar[list] = []
    ignore_update = False

    def __init__(self, a: sparse.csr_matrix, b: np.ndarray):
        self.a, self.b = a.copy(), b.copy()
        self.plans = 0
        self.freed = False
        self.factor = None
        self.instances.append(self)

    def plan(self):
        self.plans += 1

    def factorize(self):
        assert self.plans
        self.factor = splu(self.a.tocsc())

    def solve(self):
        assert self.factor is not None
        return self.factor.solve(self.b)

    def reset_operands(self, *, a: sparse.csr_matrix | None = None, b: np.ndarray | None = None):
        if a is not None and not self.ignore_update:
            self.a = a.copy()
        if b is not None:
            self.b = b.copy()

    def free(self):
        assert not self.freed
        self.freed = True


@pytest.fixture
def solvers(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(CpuSolver, "instances", [])
    monkeypatch.setattr(CpuSolver, "ignore_update", False)
    advanced = ModuleType("nvmath.sparse.advanced")
    monkeypatch.setattr(advanced, "DirectSolver", CpuSolver, raising=False)
    for name in ("nvmath", "nvmath.sparse"):
        monkeypatch.setitem(sys.modules, name, ModuleType(name))
    monkeypatch.setitem(sys.modules, "nvmath.sparse.advanced", advanced)
    return CpuSolver


@pytest.fixture
def matrix():
    return sparse.csr_matrix([[4.0, -1.0, 0.0], [-1.0, 5.0, -1.0], [0.0, -1.0, 3.0]])


def test_baseline_does_not_leak_discarded_factorizations(
    script: ModuleType, solvers: type[CpuSolver], matrix: sparse.csr_matrix
):
    _, solve, _ = script.time_cudss(matrix, np.ones(3))
    solve(np.ones(3))
    assert all(s.freed for s in solvers.instances[:-1])


def test_value_updates_change_numbers_without_changing_pattern(script: ModuleType, matrix: sparse.csr_matrix):
    updates = list(script.value_updates(matrix, 3))
    assert len(updates) == 3
    for updated in updates:
        np.testing.assert_array_equal(updated.indptr, matrix.indptr)
        np.testing.assert_array_equal(updated.indices, matrix.indices)
        assert not np.array_equal(updated.data, matrix.data)
    assert not np.array_equal(updates[0].data, updates[1].data)
    np.testing.assert_array_equal(matrix.toarray(), [[4, -1, 0], [-1, 5, -1], [0, -1, 3]])


def test_updated_values_are_solved_and_analysis_reused(
    script: ModuleType, solvers: type[CpuSolver], matrix: sparse.csr_matrix
):
    results = script.cudss_updates(matrix, np.ones(3), script.value_updates(matrix, 3))
    assert len(results) == 3
    assert sum(s.plans for s in solvers.instances) == 1
    assert all(s.freed for s in solvers.instances)
    assert all(r.relative_error < 1e-12 and r.backward_error < 1e-12 for r in results)
    assert all(not r.replanned for r in results)


def test_stale_values_fail_correctness_instead_of_producing_timings(
    script: ModuleType, solvers: type[CpuSolver], matrix: sparse.csr_matrix, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(solvers, "ignore_update", True)
    with pytest.raises(AssertionError, match="CPU reference"):
        script.cudss_updates(matrix, np.ones(3), script.value_updates(matrix, 2))
    assert all(s.freed for s in solvers.instances)


def test_new_sparsity_recreates_analysis_even_at_same_nnz(
    script: ModuleType, solvers: type[CpuSolver], matrix: sparse.csr_matrix
):
    other = matrix.copy()
    other.indices[1] = 2  # Move an off-diagonal entry without changing nnz.
    other.sort_indices()
    results = script.cudss_updates(matrix, np.ones(3), [other])
    assert results[0].replanned
    assert sum(s.plans for s in solvers.instances) == 2
    assert all(s.freed for s in solvers.instances)


def test_failure_during_factorization_releases_resources(
    script: ModuleType, solvers: type[CpuSolver], matrix: sparse.csr_matrix, monkeypatch: pytest.MonkeyPatch
):
    def fail(_self: CpuSolver):
        msg = "factorization failed"
        raise RuntimeError(msg)

    monkeypatch.setattr(solvers, "factorize", fail)
    with pytest.raises(RuntimeError, match="factorization failed"):
        script.cudss_updates(matrix, np.ones(3), script.value_updates(matrix, 1))
    assert all(s.freed for s in solvers.instances)


def test_baseline_releases_retained_solver_when_finished(
    script: ModuleType, solvers: type[CpuSolver], matrix: sparse.csr_matrix
):
    with ExitStack() as resources:
        _, solve, label = script.time_cudss(matrix, np.ones(3), resources=resources)
        np.testing.assert_allclose(solve(np.ones(3)), np.linalg.solve(matrix.toarray(), np.ones(3)))
        assert "unchanged" in label
    assert all(s.freed for s in solvers.instances)


def test_unchanged_or_nonfinite_values_are_rejected(
    script: ModuleType, solvers: type[CpuSolver], matrix: sparse.csr_matrix
):
    with pytest.raises(ValueError, match="unchanged"):
        script.cudss_updates(matrix, np.ones(3), [matrix.copy()])
    invalid = matrix.copy()
    invalid.data[0] = np.nan
    with pytest.raises(ValueError, match="finite"):
        script.cudss_updates(matrix, np.ones(3), [invalid])
    assert all(s.freed for s in solvers.instances)


@given(size=st.integers(min_value=2, max_value=10), count=st.integers(min_value=1, max_value=5))
def test_row_updates_preserve_nonzero_pattern_and_nonsingularity(size: int, count: int):
    path = Path(__file__).resolve().parents[1] / "scripts"
    original = sys.path[:]
    sys.path.insert(0, str(path))
    try:
        value_updates = importlib.import_module("solver_factorize").value_updates
    finally:
        sys.path[:] = original
    matrix = sparse.eye(size, format="csr")
    for updated in value_updates(matrix, count):
        np.testing.assert_array_equal(updated.indptr, matrix.indptr)
        np.testing.assert_array_equal(updated.indices, matrix.indices)
        assert np.all(updated.data > 0)
        assert not np.array_equal(updated.data, matrix.data)


@pytest.mark.parametrize("solution", [np.ones(1), np.full(3, np.nan)])
def test_invalid_solution_is_rejected(
    script: ModuleType,
    solvers: type[CpuSolver],
    matrix: sparse.csr_matrix,
    monkeypatch: pytest.MonkeyPatch,
    solution: np.ndarray,
):
    monkeypatch.setattr(solvers, "solve", lambda _self: solution)
    with pytest.raises(AssertionError, match="CPU reference"):
        script.cudss_updates(matrix, np.ones(3), script.value_updates(matrix, 1))
    assert all(s.freed for s in solvers.instances)


def test_empty_updates_fail_instead_of_successful_empty_report(
    script: ModuleType, solvers: type[CpuSolver], matrix: sparse.csr_matrix
):
    with pytest.raises(ValueError, match="At least one"):
        script.cudss_updates(matrix, np.ones(3), [])
    assert all(s.freed for s in solvers.instances)


def test_baseline_cleanup_is_outside_first_factorization_samples(
    script: ModuleType, solvers: type[CpuSolver], matrix: sparse.csr_matrix, monkeypatch: pytest.MonkeyPatch
):
    clock = [0.0]
    plan, factorize, free = solvers.plan, solvers.factorize, solvers.free

    def slow_plan(solver: CpuSolver):
        clock[0] += 2
        plan(solver)

    def slow_factorize(solver: CpuSolver):
        clock[0] += 3
        factorize(solver)

    def slow_free(solver: CpuSolver):
        clock[0] += 100
        free(solver)

    monkeypatch.setattr(solvers, "plan", slow_plan)
    monkeypatch.setattr(solvers, "factorize", slow_factorize)
    monkeypatch.setattr(solvers, "free", slow_free)
    monkeypatch.setattr(script.time, "perf_counter", lambda: clock[0])
    with ExitStack() as resources:
        first_s, _solve, _label = script.time_cudss(matrix, np.ones(3), resources=resources)
    assert first_s == 5
    assert all(s.freed for s in solvers.instances)
