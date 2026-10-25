"""bw2calc: single scores, multiple scores and Monte Carlo on synthetic systems.

The solver is whatever the asv environment installs (PyPardiso, UMFPACK or SuperLU),
because bw2calc picks it at import. Every case checks its scores against the float64
reference in ``reference.json``, outside the timed call, and the ``track_relative_error``
results record the relative error, so a wrong answer shows up in the history next to a
fast one. Each setup also solves once before the timed call, so one-time costs (imports,
first loads) stay out of the first sample.
"""

import inspect
import warnings

import bw2calc as bc
import numpy as np
from scipy import sparse
from scipy.sparse.linalg import cgs

from bwbench import DIRECT_RTOL, ITERATIVE_RTOL, check, check_table, first_time, knob
from bwbench.asv import classes
from bwbench.bench import BenchSetup, bench
from bwbench.synth import method_name, neumann_score, packages, skip_unless_factorizable

CLASSES = ["LCA", "IterativeLCA", "JacobiGMRESLCA"]
SIZES = knob("sizes", "smoke")
MC_SIZES = knob("mc_sizes", "smoke")


def solver() -> str:
    """The direct solver bw2calc chose at import."""
    if bc.PYPARDISO:
        return "pypardiso"
    return "umfpack" if getattr(bc, "UMFPACK", False) else "superlu"


def rtol_for(cls: str) -> float:
    """The check's tolerance: direct solves for ``LCA``, iterative ones for the others."""
    return DIRECT_RTOL if cls == "LCA" else ITERATIVE_RTOL


def lca_class(name: str) -> type:
    """A bw2calc class by name; asv skips the case when this release lacks it."""
    if not hasattr(bc, name):
        raise NotImplementedError(f"bw2calc {bc.__version__} has no {name}")
    return getattr(bc, name)


def _source_has(fn: object, text: str) -> bool:
    try:
        return text in inspect.getsource(fn)
    except (OSError, TypeError):
        return False


def skip_known_crash(cls: str, *, calls_next: bool) -> None:
    """Skip a case this release crashes on for a reason already reported upstream.

    asv records a ``NotImplementedError`` in setup as skipped, so the history shows a gap with
    the link instead of a failure. Each test looks at behaviour, not at the version number, so
    a release with the fix runs the case again. ``calls_next``: the case calls ``next()``, the
    only path that frees PyPardiso's factorization.
    """
    if cls == "IterativeLCA" and _source_has(bc.IterativeLCA.solve_linear_system, '"legacy"'):
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                cgs(sparse.identity(1, format="csr"), np.ones(1), atol="legacy")
        except (TypeError, ValueError):
            raise NotImplementedError(
                f"bw2calc {bc.__version__} passes atol='legacy' to cgs, which this scipy rejects: "
                "https://github.com/brightway-lca/brightway2-calc/pull/161#issuecomment-6140609983"
            ) from None
    free = getattr(bc.LCA, "_delete_solver_state", None)  # from bw2calc 2.3
    if free is None and cls == "FastScoresOnlyMultiLCA":
        free = bc.FastScoresOnlyMultiLCA.__next__  # bw2calc 2.2 frees the factorization here
    if (
        calls_next
        and cls in {"JacobiGMRESLCA", "FastScoresOnlyMultiLCA"}
        and bc.PYPARDISO
        and _source_has(free, "free_memory")
        and not _source_has(free, "PyPardisoError")
    ):
        raise NotImplementedError(
            f"bw2calc {bc.__version__} frees a PyPardiso factorization that {cls} never made: "
            "https://github.com/brightway-lca/brightway2-calc/issues/157"
        )


def score_of(scores: object, method: tuple, demand: str) -> float:
    """One score from MultiLCA (a dict) or FastScoresOnlyMultiLCA (an xarray)."""
    if hasattr(scores, "sel"):
        return float(scores.sel(LCIA=str(method), processes=demand))
    return float(scores[(method, demand)])


# Every case below starts from a fresh setup: the seam runs `run` once per setup, so the
# iterative classes never start from the answer of the last call.


@bench({"size": SIZES, "cls": CLASSES}, error="relative_error", asv="SingleScore", timeout=600, peakmem=True)
def first_score(size: str, cls: str) -> BenchSetup:
    """One demand, one method: build the matrices, factorize, solve, characterize."""
    # The setup solves once before the timed call; JacobiGMRESLCA solves by GMRES, not LU.
    skip_unless_factorizable(size, pardiso=bc.PYPARDISO, factorizations=0 if cls == "JacobiGMRESLCA" else 2)
    lca_cls = lca_class(cls)
    inventory, methods, refs, _ = packages(size)
    rtol = rtol_for(cls)

    def run() -> float:
        lca = lca_cls(demand={0: 1}, data_objs=[inventory, methods[0]])
        lca.lci()
        lca.lcia()
        return float(lca.score)

    def against_reference(score: float) -> float:
        return check(score, refs[0][0], rtol, f"score ({solver()})")

    if first_time("first_score", size, cls):  # also the warm-up before the first timed call
        against_reference(run())
    return run, against_reference


@bench({"size": SIZES, "cls": CLASSES}, error="relative_error", asv="NewDemand", fresh_solver=False, timeout=600)
def redo_lci(size: str, cls: str) -> BenchSetup:
    """A second demand on a system already solved once: the solve alone.

    For ``IterativeLCA`` before bw2calc 3.0 this is the first CGS solve, warm-started from
    the first demand's supply; its first solve is a direct one. From 3.0 it solves a new
    demand on an unchanged matrix directly, with the factorization of that first solve.
    """
    skip_unless_factorizable(size, pardiso=bc.PYPARDISO)  # lci(factorize=True), for every class
    skip_known_crash(cls, calls_next=False)
    inventory, methods, refs, _ = packages(size)
    rtol = rtol_for(cls)
    lca = lca_class(cls)(demand={0: 1}, data_objs=[inventory, methods[0]])
    lca.lci(factorize=True)
    lca.lcia()

    def run() -> None:
        lca.redo_lci({1: 1})

    def against_reference(_: None) -> float:
        score = float((lca.characterization_matrix @ lca.inventory).sum())
        return check(score, refs[1][0], rtol, f"second-demand score ({solver()})")

    return run, against_reference


@bench({"size": SIZES, "demands": [1, 3, 10, 30], "variant": ["MultiLCA", "forward", "adjoint"]}, asv="MultiScores")
def scores(size: str, demands: int, variant: str) -> BenchSetup:
    """Many demands against three methods, with MultiLCA and FastScoresOnlyMultiLCA.

    ``direction`` is the forward/adjoint switch of bw2calc PR #165. Its ``"auto"`` rule
    picks adjoint when there are more demands than impact categories (3 here), so the
    demand counts straddle that threshold.
    """
    skip_unless_factorizable(size, pardiso=bc.PYPARDISO, factorizations=2)
    inventory, methods, refs, _ = packages(size)
    config = {"impact_categories": [method_name(i) for i in range(len(methods))]}
    wanted = {f"d{i}": {i: 1} for i in range(demands)}
    kwargs = {}
    if variant == "MultiLCA":
        lca_cls = bc.MultiLCA
    else:
        lca_cls = lca_class("FastScoresOnlyMultiLCA")
        skip_known_crash("FastScoresOnlyMultiLCA", calls_next=True)
        if not (bc.PYPARDISO or getattr(bc, "UMFPACK", False)):
            raise NotImplementedError("FastScoresOnlyMultiLCA needs PARDISO or UMFPACK")
        if "direction" in inspect.signature(lca_cls.__init__).parameters:
            kwargs["direction"] = variant
        elif variant == "adjoint":
            raise NotImplementedError(f"bw2calc {bc.__version__} has no adjoint direction")

    def run() -> object:
        lca = lca_cls(demands=wanted, method_config=config, data_objs=[inventory, *methods], **kwargs)
        if lca_cls is not bc.MultiLCA:
            next(lca)  # FastScoresOnlyMultiLCA has no separate lci/lcia
        else:
            lca.lci()
            lca.lcia()
        return lca.scores

    def against_reference(result: object) -> float:
        table = [[score_of(result, method_name(m), f"d{d}") for m in range(len(methods))] for d in range(demands)]
        return check_table(table, refs[:demands], DIRECT_RTOL, f"score ({solver()})")

    if first_time("scores", size, demands, variant):  # also the warm-up before the first timed call
        against_reference(run())
    return run, against_reference


@bench(
    {"size": MC_SIZES, "iterations": knob("iterations", "10", int), "cls": CLASSES},
    asv="MonteCarlo",
    fresh_solver=False,
    timeout=1800,
    repeat=(1, 5, 600),
)
def iterations(size: str, iterations: int, cls: str) -> BenchSetup:
    """``iterations`` Monte Carlo draws after the first score.

    #131 names Monte Carlo at the 100k-product size (``BWBENCH_MC_SIZES=mc100k``) as the
    case worth benchmarking. BenchSetup checks one draw against a Neumann solve of that draw's
    matrix, and that the draw differs from the static score.
    """
    # LCA refactorizes on every draw; IterativeLCA factorizes once; JacobiGMRESLCA never.
    draws = {"LCA": iterations + 2, "IterativeLCA": 1}.get(cls, 0)
    skip_unless_factorizable(size, pardiso=bc.PYPARDISO, factorizations=draws)
    skip_known_crash(cls, calls_next=True)
    inventory, methods, refs, scale = packages(size, uncertain=True)
    lca = lca_class(cls)(demand={0: 1}, data_objs=[inventory, methods[0]], use_distributions=True, seed_override=1)
    lca.lci()
    lca.lcia()
    next(lca)
    if first_time("iterations", size, iterations, cls):  # the same draw (seed_override) every sample
        # Product ids are 0 to n - 1, so bw2calc's matrix order is the id order of `scale`.
        check(float(lca.score), neumann_score(lca, scale), rtol_for(cls), f"Monte Carlo score ({solver()})")
        if abs(lca.score - refs[0][0]) <= ITERATIVE_RTOL * abs(refs[0][0]):
            raise AssertionError("the Monte Carlo draw equals the static score: distributions were ignored")

    def run() -> float:
        for _ in range(iterations):
            next(lca)
        return float(lca.score)

    def finite(score: float) -> None:
        if not np.isfinite(score):
            raise AssertionError("non-finite Monte Carlo score")

    return run, finite


classes(__name__)
