"""bw2calc: single scores, multiple scores and Monte Carlo on synthetic systems.

The solver is whatever the asv environment installs (PyPardiso, UMFPACK or SuperLU),
because bw2calc picks it at import. Every setup checks the score against the SuperLU
reference in ``reference.json`` before anything is timed, and the ``track_`` results
record the relative error, so a wrong answer shows up in the history next to a fast one.
"""

import inspect

import bw2calc as bc
import numpy as np
from scipy import sparse

from bwbench import DIRECT_RTOL, ITERATIVE_RTOL, check, knob
from bwbench.synth import GENERATOR_VERSION, cached, load, method_name, neumann

CLASSES = ["LCA", "IterativeLCA", "JacobiGMRESLCA"]


def solver() -> str:
    """The direct solver bw2calc chose at import."""
    if bc.PYPARDISO:
        return "pypardiso"
    return "umfpack" if getattr(bc, "UMFPACK", False) else "superlu"


def lca_class(name: str) -> type:
    """A bw2calc class by name; asv skips the case when this release lacks it."""
    if not hasattr(bc, name):
        raise NotImplementedError(f"bw2calc {bc.__version__} has no {name}")
    return getattr(bc, name)


def score_of(scores: object, method: tuple, demand: str) -> float:
    """One score from MultiLCA (a dict) or FastScoresOnlyMultiLCA (an xarray)."""
    if hasattr(scores, "sel"):
        return float(scores.sel(LCIA=str(method), processes=demand))
    return float(scores[(method, demand)])


class SingleScore:
    """One demand, one method: build the matrices, factorize, solve, characterize."""

    version = GENERATOR_VERSION
    params = (knob("sizes", "smoke"), CLASSES)
    param_names = ["size", "cls"]
    timeout = 600

    def setup(self, size: str, cls: str) -> None:
        self.cls = lca_class(cls)
        self.inventory, methods, refs = load(cached(size))
        self.method, self.reference = methods[0], refs[0][0]
        self.rtol = DIRECT_RTOL if cls == "LCA" else ITERATIVE_RTOL
        self.err = check(self._score(), self.reference, self.rtol, f"score ({solver()})")

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
    """A second demand on a system already factorized: the solve alone."""

    version = GENERATOR_VERSION
    params = (knob("sizes", "smoke"),)
    param_names = ["size"]
    timeout = 600

    def setup(self, size: str) -> None:
        inventory, methods, _ = load(cached(size))
        self.lca = bc.LCA(demand={0: 1}, data_objs=[inventory, methods[0]])
        self.lca.lci(factorize=True)
        self.lca.lcia()

    def time_redo_lci(self, size: str) -> None:
        self.lca.redo_lci({1: 1})


class MultiScores:
    """Many demands against three methods, with MultiLCA and FastScoresOnlyMultiLCA.

    ``direction`` is the forward/adjoint switch of bw2calc PR #165. Its ``"auto"`` rule
    picks adjoint when there are more demands than impact categories (3 here), so the
    demand counts straddle that threshold.
    """

    version = GENERATOR_VERSION
    params = (knob("sizes", "smoke"), [1, 3, 10, 30], ["MultiLCA", "forward", "adjoint"])
    param_names = ["size", "demands", "variant"]
    timeout = 900

    def setup(self, size: str, demands: int, variant: str) -> None:
        inventory, methods, refs = load(cached(size))
        self.data_objs = [inventory, *methods]
        self.config = {"impact_categories": [method_name(i) for i in range(len(methods))]}
        self.demands = {f"d{i}": {i: 1} for i in range(demands)}
        self.kwargs = {}
        if variant == "MultiLCA":
            self.cls = bc.MultiLCA
        else:
            self.cls = lca_class("FastScoresOnlyMultiLCA")
            if not (bc.PYPARDISO or getattr(bc, "UMFPACK", False)):
                raise NotImplementedError("FastScoresOnlyMultiLCA needs PARDISO or UMFPACK")
            if "direction" in inspect.signature(self.cls.__init__).parameters:
                self.kwargs["direction"] = variant
            elif variant == "adjoint":
                raise NotImplementedError(f"bw2calc {bc.__version__} has no adjoint direction")
        scores = self._scores()
        for i, ref in enumerate(refs[0]):
            check(score_of(scores, method_name(i), "d0"), ref, DIRECT_RTOL, f"score ({solver()})")

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
    case worth benchmarking. Setup checks one draw against a Neumann solve of that draw's matrix.
    """

    version = GENERATOR_VERSION
    params = (knob("mc_sizes", "smoke"), [int(x) for x in knob("iterations", "10")], CLASSES)
    param_names = ["size", "iterations", "cls"]
    timeout = 1800
    number = 1
    repeat = (1, 5, 600)

    def setup(self, size: str, iterations: int, cls: str) -> None:
        inventory, methods, _ = load(cached(size, uncertain=True))
        self.lca = lca_class(cls)(
            demand={0: 1}, data_objs=[inventory, methods[0]], use_distributions=True, seed_override=1
        )
        self.lca.lci()
        self.lca.lcia()
        next(self.lca)
        a = self.lca.technosphere_matrix
        supply = neumann(sparse.identity(a.shape[0], format="csr") - a, self.lca.demand_array)
        expected = float((self.lca.characterization_matrix @ self.lca.biosphere_matrix @ supply).sum())
        rtol = DIRECT_RTOL if cls == "LCA" else ITERATIVE_RTOL
        check(float(self.lca.score), expected, rtol, f"Monte Carlo score ({solver()})")

    def time_iterations(self, size: str, iterations: int, cls: str) -> None:
        for _ in range(iterations):
            next(self.lca)
        if not np.isfinite(self.lca.score):
            raise AssertionError("non-finite Monte Carlo score")
