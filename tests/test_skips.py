"""skip_known_crash against stub bw2calc releases: bw2calc itself is never installed on the host."""

import importlib.util
import sys
import types
from pathlib import Path

import pytest

BENCH = Path(__file__).resolve().parents[1] / "benchmarks" / "bench_bw2calc" / "bench_lca.py"


# bench_lca reads only the source text of bw2calc's methods, so each stub's docstring holds it.
def legacy_solve(_self: object) -> None:
    """cgs(A, b, x0=guess, atol="legacy", maxiter=1000)."""


def frees_pardiso(_self: object) -> None:
    """pypardiso_solver.free_memory()."""


def frees_pardiso_tolerantly(_self: object) -> None:
    """Try pypardiso_solver.free_memory(), except PyPardisoError: pass."""


def load(monkeypatch: pytest.MonkeyPatch, *, pardiso: bool = True, delete: object = frees_pardiso) -> types.ModuleType:
    bc = types.ModuleType("bw2calc")
    bc.__dict__.update(
        __version__="stub",
        PYPARDISO=pardiso,
        IterativeLCA=type("IterativeLCA", (), {"solve_linear_system": legacy_solve}),
        LCA=type("LCA", (), {} if delete is None else {"_delete_solver_state": delete}),
    )
    monkeypatch.setitem(sys.modules, "bw2calc", bc)
    spec = importlib.util.spec_from_file_location("bench_lca_under_test", BENCH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("cls", ["JacobiGMRESLCA", "FastScoresOnlyMultiLCA"])
def test_pardiso_crash_skips_only_cases_that_call_next(monkeypatch: pytest.MonkeyPatch, cls: str):
    bench = load(monkeypatch)
    with pytest.raises(NotImplementedError, match="issues/157"):
        bench.skip_known_crash(cls, calls_next=True)
    bench.skip_known_crash(cls, calls_next=False)  # redo_lci never frees the factorization


@pytest.mark.parametrize(
    ("pardiso", "delete"),
    [
        (False, frees_pardiso),  # PyPardiso not installed
        (True, None),  # bw2calc 2.2: no _delete_solver_state
        (True, frees_pardiso_tolerantly),  # bw2calc main since #159
    ],
)
def test_pardiso_crash_not_skipped_where_it_cannot_happen(
    monkeypatch: pytest.MonkeyPatch, *, pardiso: bool, delete: object
):
    load(monkeypatch, pardiso=pardiso, delete=delete).skip_known_crash("JacobiGMRESLCA", calls_next=True)


def test_atol_legacy_skipped_where_scipy_rejects_it(monkeypatch: pytest.MonkeyPatch):
    # The host's scipy (>= 1.18) rejects atol="legacy".
    with pytest.raises(NotImplementedError, match="pull/161"):
        load(monkeypatch).skip_known_crash("IterativeLCA", calls_next=False)
