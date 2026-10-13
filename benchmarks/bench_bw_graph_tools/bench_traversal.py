"""bw_graph_tools: supply-chain traversal on a synthetic system.

``max_calc=2`` is the small case that PR #55 slowed from 0.04 s to 1.05 s, because a
transposed solve threw away the factorization ``lci()`` already had. Always time it
next to the large case.
"""

import bw2calc as bc
from bw_graph_tools import GraphTraversalSettings, NewNodeEachVisitGraphTraversal

from bwbench import knob
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
        if abs(self.lca.score - refs[0][0]) > 1e-9 * abs(refs[0][0]):
            raise AssertionError("LCA score differs from the reference")
        self.settings = GraphTraversalSettings(max_calc=max_calc, cutoff=1e-3)

    def time_traverse(self, size: str, max_calc: int) -> None:
        NewNodeEachVisitGraphTraversal(self.lca, self.settings).traverse()
