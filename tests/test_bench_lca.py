import importlib.metadata
import importlib.util
import sys
import types
from pathlib import Path

import numpy as np
import pytest
from scipy import sparse

from bwbench.bench import NotApplicable

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


def test_multilca_runs_at_one_demand_count_only(bench_lca: types.ModuleType, monkeypatch: pytest.MonkeyPatch):
    """MultiLCA has no forward/adjoint switch, so its 1 and 10 demand counts would repeat one factorization."""

    class ReachedError(Exception):
        pass

    def reached(*_: object, **__: object) -> None:
        raise ReachedError

    monkeypatch.setattr(bench_lca, "skip_unless_factorizable", reached)
    for demands in (1, 10):
        with pytest.raises(NotApplicable, match="MultiLCA runs at 30"):
            bench_lca.scores.prepare(size="smoke", demands=demands, variant="MultiLCA")
    for demands, variant in [(30, "MultiLCA"), (1, "forward"), (1, "adjoint")]:
        with pytest.raises(ReachedError):
            bench_lca.scores.prepare(size="smoke", demands=demands, variant=variant)


def test_fast_scores_on_another_solver_is_not_applicable(bench_lca: types.ModuleType, monkeypatch: pytest.MonkeyPatch):
    """BWBENCH_STRICT fails a plain NotImplementedError, so a case for another solver must say NotApplicable."""

    class FastScoresOnlyMultiLCA(StubLCA):
        def __init__(self, demands: dict, data_objs: list, direction: str = "forward") -> None:  # noqa: ARG002
            super().__init__(demands, data_objs)

    monkeypatch.setattr(bench_lca.bc, "FastScoresOnlyMultiLCA", FastScoresOnlyMultiLCA, raising=False)
    monkeypatch.setattr(bench_lca, "skip_known_crash", lambda *_, **__: None)
    with pytest.raises(NotApplicable, match="PARDISO or UMFPACK"):
        bench_lca.fast_scores("forward")
    monkeypatch.setattr(bench_lca.bc, "UMFPACK", True, raising=False)
    monkeypatch.setenv("BWBENCH_SOLVER", "umfpack-T")
    with pytest.raises(NotApplicable, match="umfpack-T"):
        bench_lca.fast_scores("adjoint")


def test_condition_estimate_runs_in_the_superlu_environment_only(
    bench_lca: types.ModuleType, monkeypatch: pytest.MonkeyPatch
):
    """Under asv every environment has the same SciPy, so only the SuperLU one records the estimate."""
    installed: set[str] = set()

    def version(dist: str) -> str:
        if dist not in installed:
            raise importlib.metadata.PackageNotFoundError(dist)
        return "1"

    monkeypatch.setattr(importlib.metadata, "version", version)
    monkeypatch.setattr(bench_lca, "skip_unless_factorizable", lambda *_, **__: None)
    monkeypatch.setattr(bench_lca, "system", lambda _size: types.SimpleNamespace(condition_estimate=lambda: 1.0))
    monkeypatch.delenv("BWBENCH_SOLVER", raising=False)
    monkeypatch.setenv("ASV", "true")
    assert bench_lca.condition_estimate.prepare(size="smoke")() == 1.0
    for dist in ("pypardiso", "scikit-umfpack"):
        installed = {dist}
        with pytest.raises(NotApplicable, match="SuperLU environment"):
            bench_lca.condition_estimate.prepare(size="smoke")
    # Outside asv (CodSpeed, compat) there is one environment, which keeps the case.
    monkeypatch.delenv("ASV")
    assert bench_lca.condition_estimate.prepare(size="smoke")() == 1.0
    monkeypatch.setenv("ASV", "true")
    installed = set()
    monkeypatch.setenv("BWBENCH_SOLVER", "klu")
    with pytest.raises(NotApplicable, match="SuperLU environment"):
        bench_lca.condition_estimate.prepare(size="smoke")


def test_qmc_draws_use_the_complete_scrambled_sobol_block(bench_lca: types.ModuleType):
    from scipy.special import ndtri  # noqa: PLC0415
    from scipy.stats import qmc  # noqa: PLC0415

    loc, scale = np.array([2.0, -3.0]), np.array([0.2, 0.3])
    draws = bench_lca.NormalDraws(loc, scale, "sobol", seed=7)
    actual = np.array([next(draws) for _ in range(16)])
    expected = loc + scale * ndtri(qmc.Sobol(2, scramble=True, rng=7).random_base2(4))
    np.testing.assert_allclose(actual, expected, rtol=1e-14, atol=1e-14, strict=True)
    draws.reset()
    np.testing.assert_allclose(next(draws), expected[0], rtol=1e-14, atol=1e-14, strict=True)


def test_qmc_convergence_checks_the_draw_and_tracks_error_without_more_sampling(
    bench_lca: types.ModuleType, monkeypatch: pytest.MonkeyPatch
):
    draws = bench_lca.NormalDraws(np.array([2.0]), np.array([0.2]), "sobol", seed=1)

    class SampleLCA:
        score = 0.0

        def __next__(self):
            self.score = float(next(draws)[0])

    lca = SampleLCA()
    next(lca)  # setup has already consumed a sample
    checked = []
    monkeypatch.setattr(bench_lca, "sampled_lca", lambda *_: (lca, draws, np.ones(1), 1.0))
    monkeypatch.setattr(bench_lca, "mean_reference", lambda _: 2.0)
    monkeypatch.setattr(bench_lca, "neumann_score", lambda *_: lca.score)
    monkeypatch.setattr(bench_lca, "reached_patch", lambda _: checked.append(True))
    prepared = bench_lca.convergence.prepare(size="smoke", draws=16, cls="LCA", sampler="sobol")
    result = prepared()
    prepared.verify(result)
    assert checked
    expected = bench_lca.NormalDraws(np.array([2.0]), np.array([0.2]), "sobol", seed=1)
    np.testing.assert_allclose(result[0], [next(expected)[0] for _ in range(16)], rtol=1e-14, atol=1e-14)
    error = bench_lca.convergence.track["relative_mean_error"](result)
    assert error == pytest.approx(abs(np.mean(result[0]) / 2.0 - 1), rel=1e-14, abs=1e-14)


def test_qmc_skips_other_sizes_before_building_a_reference(
    bench_lca: types.ModuleType, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(bench_lca, "mean_reference", lambda _: pytest.fail("unexpected reference build"))
    with pytest.raises(NotApplicable, match="smoke size only"):
        bench_lca.convergence.prepare(size="mc100k", draws=16, cls="LCA", sampler="sobol")


@pytest.mark.parametrize("types_", [[0], [4], [3] * 21202])
def test_qmc_rejects_unsupported_distribution_shapes(
    bench_lca: types.ModuleType, monkeypatch: pytest.MonkeyPatch, types_: list[int]
):
    monkeypatch.setitem(sys.modules, "bw_processing", types.ModuleType("bw_processing"))
    distribution = np.array([(n,) for n in types_], dtype=[("uncertainty_type", "u1")])
    inventory = types.SimpleNamespace(get_resource=lambda _: (distribution, {}))
    monkeypatch.setattr(bench_lca, "packages", lambda *_args, **_kwargs: (inventory, [], [], np.ones(1)))
    with pytest.raises(NotApplicable, match=r"normal input|dimension limit"):
        bench_lca.sampled_lca("smoke", "LCA", "sobol")
