"""bw_graph_tools: supply-chain traversal on a synthetic system.

``max_calc=2`` is the small case that PR #55 slowed from 0.04 s to 1.05 s, because a
transposed solve threw away the factorization ``lci()`` already had. Always time it
next to the large case.
"""

import bw2calc as bc
from bw_graph_tools import GraphTraversalSettings, NewNodeEachVisitGraphTraversal

from bwbench import DIRECT_RTOL, check, knob
from bwbench.synth import GENERATOR_VERSION, cached, load


class Traversal:
    version = GENERATOR_VERSION
    params = (knob("sizes", "smoke"), [2, 100])
    param_names = ["size", "max_calc"]
    timeout = 900

    def setup(self, size: str, max_calc: int) -> None:
        inventory, methods, refs = load(cached(size))
        self.lca = bc.LCA(demand={0: 1}, data_objs=[inventory, methods[0]])
        self.lca.lci()
        self.lca.lcia()
        check(self.lca.score, refs[0][0], DIRECT_RTOL, "LCA score")
        self.settings = GraphTraversalSettings(max_calc=max_calc, cutoff=1e-3)

    def time_traverse(self, size: str, max_calc: int) -> None:
        NewNodeEachVisitGraphTraversal(self.lca, self.settings).traverse()

    def track_calculation_count(self, size: str, max_calc: int) -> int:
        """The traversal's counter: one per node above the cutoff; it stops once past ``max_calc``.

        A count well under ``max_calc`` means the cutoff ended the traversal first, so the
        case does not test the ``max_calc`` limit.
        """
        traversal = NewNodeEachVisitGraphTraversal(self.lca, self.settings)
        traversal.traverse()
        if not hasattr(traversal, "calculation_count"):
            raise NotImplementedError("this bw_graph_tools release has no calculation_count")
        return traversal.calculation_count
