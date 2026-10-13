"""bw2calc: single scores, multiple scores and Monte Carlo on synthetic systems.

The solver is whatever the asv environment installs (PyPardiso, UMFPACK or SuperLU),
because bw2calc picks it at import. Every case checks its scores against the float64
reference in ``reference.json``, in setup or in its ``track_`` result, and the ``track_``
results record the relative error, so a wrong answer shows up in the history next to a
fast one.
"""

import inspect
import warnings

import bw2calc as bc
import numpy as np
from scipy import sparse
from scipy.sparse.linalg import cgs

from bwbench import DIRECT_RTOL, ITERATIVE_RTOL, check, check_table, knob
from bwbench.synth import method_name, neumann, packages, profile_version

CLASSES = ["LCA", "IterativeLCA", "JacobiGMRESLCA"]
SIZES = knob("sizes", "smoke")
MC_SIZES = knob("mc_sizes", "smoke")


def solver() -> str:
    """The direct solver bw2calc chose at import."""
    if bc.PYPARDISO:
        return "pypardiso"
    return "umfpack" if getattr(bc, "UMFPACK", False) else "superlu"


def forget_factorization() -> None:
    """Drop the factorization PyPardiso keeps from the last solve.

    PyPardiso's module-level solver skips factorizing a matrix it has just factorized, so
    without this the timed call after a checking setup would skip the work that SuperLU
    and UMFPACK pay for.
    """
    if bc.PYPARDISO:
        from pypardiso.scipy_aliases import pypardiso_solver  # noqa: PLC0415

        pypardiso_solver.free_memory(everything=True)


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


class SingleScore:
    """One demand, one method: build the matrices, factorize, solve, characterize."""

    version = profile_version(SIZES)
    params = (SIZES, CLASSES)
    param_names = ["size", "cls"]
    number = 1  # with setup before every sample, each timed call starts unfactorized
    timeout = 600

    def setup(self, size: str, cls: str) -> None:
        self.cls = lca_class(cls)
        self.inventory, methods, refs, _ = packages(size)
        self.method, self.reference = methods[0], refs[0][0]
        self.rtol = DIRECT_RTOL if cls == "LCA" else ITERATIVE_RTOL
        self.err = check(self._score(), self.reference, self.rtol, f"score ({solver()})")
        forget_factorization()

    def _score(self) -> float:
        lca = self.cls(demand={0: 1}, data_objs=[self.inventory, self.method])
        lca.lci()
        lca.lcia()
        return float(lca.score)

    def time_first_score(self, size: str, cls: str) -> None:
        self._score()

    def track_relative_error(self, size: str, cls: str) -> float:
        return self.err


class NewDemand:
    """A second demand on a system already solved once: the solve alone.

    For ``IterativeLCA`` this is the first CGS solve, warm-started from the first
    demand's supply; its first solve is a direct one. ``number = 1`` and the fresh setup
    per sample keep the iterative classes from starting at the answer of the last call.
    """

    version = profile_version(SIZES)
    params = (SIZES, CLASSES)
    param_names = ["size", "cls"]
    number = 1
    timeout = 600

    def setup(self, size: str, cls: str) -> None:
        skip_known_crash(cls, calls_next=False)
        inventory, methods, refs, _ = packages(size)
        self.reference = refs[1][0]
        self.rtol = DIRECT_RTOL if cls == "LCA" else ITERATIVE_RTOL
        self.lca = lca_class(cls)(demand={0: 1}, data_objs=[inventory, methods[0]])
        self.lca.lci(factorize=True)
        self.lca.lcia()

    def time_redo_lci(self, size: str, cls: str) -> None:
        self.lca.redo_lci({1: 1})

    def track_relative_error(self, size: str, cls: str) -> float:
        self.lca.redo_lci({1: 1})
        score = float((self.lca.characterization_matrix @ self.lca.inventory).sum())
        return check(score, self.reference, self.rtol, f"second-demand score ({solver()})")


class MultiScores:
    """Many demands against three methods, with MultiLCA and FastScoresOnlyMultiLCA.

    ``direction`` is the forward/adjoint switch of bw2calc PR #165. Its ``"auto"`` rule
    picks adjoint when there are more demands than impact categories (3 here), so the
    demand counts straddle that threshold.
    """

    version = profile_version(SIZES)
    params = (SIZES, [1, 3, 10, 30], ["MultiLCA", "forward", "adjoint"])
    param_names = ["size", "demands", "variant"]
    number = 1  # as in SingleScore
    timeout = 900

    def setup(self, size: str, demands: int, variant: str) -> None:
        inventory, methods, refs, _ = packages(size)
        self.data_objs = [inventory, *methods]
        self.config = {"impact_categories": [method_name(i) for i in range(len(methods))]}
        self.demands = {f"d{i}": {i: 1} for i in range(demands)}
        self.kwargs = {}
        if variant == "MultiLCA":
            self.cls = bc.MultiLCA
        else:
            self.cls = lca_class("FastScoresOnlyMultiLCA")
            skip_known_crash("FastScoresOnlyMultiLCA", calls_next=True)
            if not (bc.PYPARDISO or getattr(bc, "UMFPACK", False)):
                raise NotImplementedError("FastScoresOnlyMultiLCA needs PARDISO or UMFPACK")
            if "direction" in inspect.signature(self.cls.__init__).parameters:
                self.kwargs["direction"] = variant
            elif variant == "adjoint":
                raise NotImplementedError(f"bw2calc {bc.__version__} has no adjoint direction")
        scores = self._scores()
        table = [[score_of(scores, method_name(m), f"d{d}") for m in range(len(methods))] for d in range(demands)]
        check_table(table, refs[:demands], DIRECT_RTOL, f"score ({solver()})")
        forget_factorization()

    def _scores(self) -> dict:
        lca = self.cls(demands=self.demands, method_config=self.config, data_objs=self.data_objs, **self.kwargs)
        if self.cls is not bc.MultiLCA:
            next(lca)  # FastScoresOnlyMultiLCA has no separate lci/lcia
        else:
            lca.lci()
            lca.lcia()
        return lca.scores

    def time_scores(self, size: str, demands: int, variant: str) -> None:
        self._scores()


class MonteCarlo:
    """``iterations`` Monte Carlo draws after the first score.

    #131 names Monte Carlo at the 100k-product size (``BWBENCH_MC_SIZES=mc100k``) as the
    case worth benchmarking. Setup checks one draw against a Neumann solve of that draw's
    matrix, and that the draw differs from the static score.
    """

    version = profile_version(MC_SIZES)
    params = (MC_SIZES, [int(x) for x in knob("iterations", "10")], CLASSES)
    param_names = ["size", "iterations", "cls"]
    timeout = 1800
    number = 1
    repeat = (1, 5, 600)

    def setup(self, size: str, iterations: int, cls: str) -> None:
        skip_known_crash(cls, calls_next=True)
        inventory, methods, refs, scale = packages(size, uncertain=True)
        self.lca = lca_class(cls)(
            demand={0: 1}, data_objs=[inventory, methods[0]], use_distributions=True, seed_override=1
        )
        self.lca.lci()
        self.lca.lcia()
        next(self.lca)
        a = self.lca.technosphere_matrix
        # Product ids are 0 to n - 1, so bw2calc's matrix order is the id order of `scale`.
        supply = neumann(sparse.identity(a.shape[0], format="csr") - a, self.lca.demand_array, scale=scale)
        expected = float((self.lca.characterization_matrix @ self.lca.biosphere_matrix @ supply).sum())
        rtol = DIRECT_RTOL if cls == "LCA" else ITERATIVE_RTOL
        check(float(self.lca.score), expected, rtol, f"Monte Carlo score ({solver()})")
        if abs(self.lca.score - refs[0][0]) <= ITERATIVE_RTOL * abs(refs[0][0]):
            raise AssertionError("the Monte Carlo draw equals the static score: distributions were ignored")

    def time_iterations(self, size: str, iterations: int, cls: str) -> None:
        for _ in range(iterations):
            next(self.lca)
        if not np.isfinite(self.lca.score):
            raise AssertionError("non-finite Monte Carlo score")
