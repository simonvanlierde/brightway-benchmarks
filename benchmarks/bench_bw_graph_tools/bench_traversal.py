"""bw_graph_tools: supply-chain traversal on a synthetic system.

``max_calc=2`` is the small case that PR #55 slowed from 0.04 s to 1.05 s, because a
transposed solve threw away the factorization ``lci()`` already had. Always time it
next to the large case, where ``max_calc=100`` binds (101 calculations at smoke size).
"""

import math

import bw2calc as bc
from bw_graph_tools import GraphTraversalSettings, NewNodeEachVisitGraphTraversal

from bwbench import DIRECT_RTOL, check, knob
from bwbench.asv import classes
from bwbench.bench import UNCHECKED, BenchSetup, bench
from bwbench.synth import packages


def calculation_count(traversal: NewNodeEachVisitGraphTraversal) -> float:
    """The traversal's counter: one per node above the cutoff; it stops once past ``max_calc``.

    A count well under ``max_calc`` means the cutoff ended the traversal first, so the
    case does not test the ``max_calc`` limit.
    """
    # NaN, not a raise: asv skips only on NotImplementedError in setup, and fails it in a track.
    return getattr(traversal, "calculation_count", math.nan)


# fresh_solver=False: reusing the factorization lci() left behind is what #55 broke.
@bench(
    {"size": knob("sizes", "smoke"), "max_calc": [2, 100]},
    track={"calculation_count": calculation_count},
    asv="Traversal",
    fresh_solver=False,
)
def traverse(size: str, max_calc: int) -> BenchSetup:
    inventory, methods, refs, _ = packages(size)
    lca = bc.LCA(demand={0: 1}, data_objs=[inventory, methods[0]])
    lca.lci()
    lca.lcia()
    check(lca.score, refs[0][0], DIRECT_RTOL, "LCA score")
    settings = GraphTraversalSettings(max_calc=max_calc, cutoff=1e-3)

    def run() -> NewNodeEachVisitGraphTraversal:
        traversal = NewNodeEachVisitGraphTraversal(lca, settings)
        traversal.traverse()
        return traversal

    return run, UNCHECKED


classes(__name__)
