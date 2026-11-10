import importlib.util
import sys
import types
from pathlib import Path

import numpy as np
import pytest
from scipy import sparse

SCRIPT = Path(__file__).resolve().parents[1] / "benchmarks" / "bench_bw2calc" / "bench_lca.py"
FACTORIZE: list[tuple[str, bool]] = []


class StubLCA:
    """Records what the setup asks of ``lci``; the timed ``redo_lci`` and the check need nothing real."""

    def __init__(self, demand: dict, data_objs: list) -> None:  # noqa: ARG002
        self.characterization_matrix = sparse.identity(1, format="csr")
        self.inventory = np.zeros((1, 1))

    def lci(self, demand: dict | None = None, factorize: bool = False) -> None:  # noqa: ARG002, FBT001, FBT002
        FACTORIZE.append((type(self).__name__, factorize))

    def lcia(self) -> None:
        pass

    def redo_lci(self, demand: dict) -> None:
        pass

    def solve_linear_system(self) -> None:
        pass


class LCA(StubLCA):
    pass


class IterativeLCA(StubLCA):
    pass


class JacobiGMRESLCA(StubLCA):
    pass


@pytest.fixture
def bench_lca(monkeypatch: pytest.MonkeyPatch) -> types.ModuleType:
    stub = types.ModuleType("bw2calc")
    vars(stub).update(LCA=LCA, IterativeLCA=IterativeLCA, JacobiGMRESLCA=JacobiGMRESLCA, PYPARDISO=False)
    stub.__version__ = "0"  # ty: ignore[unresolved-attribute]
    monkeypatch.setitem(sys.modules, "bw2calc", stub)
    spec = importlib.util.spec_from_file_location("bench_lca", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, "bench_lca", module)
    spec.loader.exec_module(module)
    monkeypatch.setattr(
        module, "packages", lambda _size: (object(), [object()], [(1.0,), (1.0,)], None)
    )  # no bw_processing here
    FACTORIZE.clear()
    return module


def test_redo_lci_factorizes_only_where_the_timed_solve_uses_it(
    bench_lca: types.ModuleType, monkeypatch: pytest.MonkeyPatch
):
    """bw2calc 2.0.2 to 3.1.0: only LCA reads ``self.solver``; IterativeLCA and JacobiGMRESLCA never do."""
    budget = []

    def record(_name: str, *, factorizations: int = 1, **_: object) -> None:
        budget.append(factorizations)

    monkeypatch.setattr(bench_lca, "skip_unless_factorizable", record)
    for cls in ("LCA", "IterativeLCA", "JacobiGMRESLCA"):
        bench_lca.redo_lci.prepare(size="smoke", cls=cls)
    assert FACTORIZE == [("LCA", True), ("IterativeLCA", False), ("JacobiGMRESLCA", False)]
    assert budget == [1, 1, 0]  # the factorizations the setup makes: the skip budget follows
