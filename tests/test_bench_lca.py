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
    stub.__version__ = "0"  # ty: ignore[missing-attribute]
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


def test_fast_scores_passes_a_direction_only_to_a_release_that_takes_one(
    bench_lca: types.ModuleType, monkeypatch: pytest.MonkeyPatch
):
    """Before bw2calc PR #165 there is no ``direction``: forward runs without it, adjoint is skipped."""

    class Directed(StubLCA):
        def __init__(self, demands: dict, data_objs: list, direction: str = "forward") -> None:  # noqa: ARG002
            super().__init__(demands, data_objs)

    class Undirected(StubLCA):
        pass

    monkeypatch.setattr(bench_lca, "skip_known_crash", lambda *_, **__: None)
    monkeypatch.setattr(bench_lca.bc, "UMFPACK", True, raising=False)
    monkeypatch.setenv("BWBENCH_SOLVER", "umfpack")
    with pytest.raises(NotImplementedError, match="no FastScoresOnlyMultiLCA"):
        bench_lca.fast_scores("forward")
    monkeypatch.setattr(bench_lca.bc, "FastScoresOnlyMultiLCA", Undirected, raising=False)
    assert bench_lca.fast_scores("forward") == (Undirected, {})
    with pytest.raises(NotImplementedError, match="no adjoint direction"):
        bench_lca.fast_scores("adjoint")
    monkeypatch.setattr(bench_lca.bc, "FastScoresOnlyMultiLCA", Directed)
    for direction in ("forward", "adjoint"):
        assert bench_lca.fast_scores(direction) == (Directed, {"direction": direction})
    monkeypatch.setattr(bench_lca.bc, "UMFPACK", False)
    monkeypatch.setattr(bench_lca.bc, "PYPARDISO", True)
    assert bench_lca.fast_scores("adjoint") == (Directed, {"direction": "adjoint"})


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
        technosphere_matrix = None
        technosphere_mm = types.SimpleNamespace(matrix=None)

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


def test_convergence_skips_a_solver_detached_from_the_sampled_matrix(
    bench_lca: types.ModuleType, monkeypatch: pytest.MonkeyPatch
):
    draws = bench_lca.NormalDraws(np.array([2.0]), np.array([0.2]), "sobol", seed=1)

    class DetachedLCA:  # JacobiGMRESLCA in bw2calc 2.4.0 and 2.5.0 solves a CSC copy
        score = 0.0
        technosphere_matrix = object()
        technosphere_mm = types.SimpleNamespace(matrix=object())

        def __next__(self):
            self.score = float(next(draws)[0])

    monkeypatch.setattr(bench_lca, "sampled_lca", lambda *_: (DetachedLCA(), draws, np.ones(1), 1.0))
    monkeypatch.setattr(bench_lca, "mean_reference", lambda _: 2.0)
    with pytest.raises(NotImplementedError, match="issues/187"):
        bench_lca.convergence.prepare(size="smoke", draws=16, cls="JacobiGMRESLCA", sampler="sobol")


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


def test_superlu_heating_sweep_is_not_applicable_after_the_size_check(monkeypatch: pytest.MonkeyPatch):
    """At a smoke size the reason is the size; at BAFU a SuperLU rebuild of 16 scenarios says NotApplicable."""
    stub = types.ModuleType("bw2calc")
    vars(stub).update(LCA=LCA, PYPARDISO=False)
    monkeypatch.setitem(sys.modules, "bw2calc", stub)
    spec = importlib.util.spec_from_file_location("bench_heating", SCRIPT.with_name("bench_heating.py"))
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, "bench_heating", module)
    spec.loader.exec_module(module)
    with pytest.raises(NotApplicable, match="BWBENCH_SIZES=bafu"):
        module.heating_sweep.prepare(size="smoke", scenarios=16, variant="rebuild")
    monkeypatch.setattr(module, "background", lambda _size: (None, {}))
    with pytest.raises(NotApplicable, match="superlu rebuild"):
        module.heating_sweep.prepare(size="bafu", scenarios=16, variant="rebuild")


def test_redo_lci_refinement_uses_calculation_config_when_available(
    bench_lca: types.ModuleType, monkeypatch: pytest.MonkeyPatch
):
    umf_pkg = types.ModuleType("scikits")
    umf_mod = types.ModuleType("scikits.umfpack")
    vars(umf_mod)["umfpack"] = types.SimpleNamespace(umfDefines={"UMFPACK_IRSTEP": 0, "UMFPACK_IR_TAKEN": 1})
    monkeypatch.setitem(sys.modules, "scikits", umf_pkg)
    monkeypatch.setitem(sys.modules, "scikits.umfpack", umf_mod)
    monkeypatch.setattr(bench_lca.bc, "UMFPACK", True, raising=False)
    monkeypatch.setattr(bench_lca.bc, "PYPARDISO", False, raising=False)
    monkeypatch.setattr(bench_lca, "skip_unless_factorizable", lambda *_a, **_kw: None)
    monkeypatch.setattr(bench_lca, "packages", lambda _size: (object(), [object()], {1: [2.0]}, None))

    seen: list[dict] = []
    context = types.SimpleNamespace(control={0: 2.0}, info={1: 0.0})

    class FakeLCA:
        characterization_matrix = np.array([[2.0]])
        inventory = np.array([[1.0]])

        def __init__(self, *, demand: object, data_objs: object, **kwargs: object) -> None:  # noqa: ARG002
            seen.append(kwargs)
            cfg = kwargs.get("calculation_config")
            if cfg is not None and not getattr(cfg, "iterative_refinement", True):
                context.control[0] = 0.0

        def lci(self, *, factorize: bool = False) -> None:
            pass

        def lcia(self) -> None:
            pass

        def redo_lci(self, _demand: object) -> None:
            pass

    monkeypatch.setattr(bench_lca.bc, "LCA", FakeLCA)
    monkeypatch.setattr(bench_lca, "umfpack_context", lambda _lca: context)

    # Older bw2calc without CalculationConfig mutates context.control directly.
    monkeypatch.delattr(bench_lca.bc, "CalculationConfig", raising=False)
    prepared = bench_lca.redo_lci_refinement.prepare(size="smoke", refinement="off")
    assert seen[-1] == {}
    assert context.control[0] == 0.0
    prepared.verify(prepared())

    # bw2calc 4.0.0+ passes CalculationConfig(iterative_refinement=...) and checks UMFPACK honoured it.
    class FakeConfig:
        def __init__(self, *, iterative_refinement: bool):
            self.iterative_refinement = iterative_refinement

    monkeypatch.setattr(bench_lca.bc, "CalculationConfig", FakeConfig, raising=False)
    context.control[0] = 2.0
    prepared_on = bench_lca.redo_lci_refinement.prepare(size="smoke", refinement="on")
    assert seen[-1]["calculation_config"].iterative_refinement is True
    assert context.control[0] == 2.0
    prepared_on.verify(prepared_on())

    prepared_off = bench_lca.redo_lci_refinement.prepare(size="smoke", refinement="off")
    assert seen[-1]["calculation_config"].iterative_refinement is False
    assert context.control[0] == 0.0
    prepared_off.verify(prepared_off())

    # If CalculationConfig(iterative_refinement=False) failed to disable UMFPACK refinement, assert.
    class BrokenLCA(FakeLCA):
        def __init__(self, *, demand: object, data_objs: object, **kwargs: object) -> None:  # noqa: ARG002
            seen.append(kwargs)

    monkeypatch.setattr(bench_lca.bc, "LCA", BrokenLCA)
    context.control[0] = 2.0
    with pytest.raises(AssertionError, match="iterative refinement enabled"):
        bench_lca.redo_lci_refinement.prepare(size="smoke", refinement="off")
