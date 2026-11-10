"""Supply-chain traversal of both heating options, over the real BAFU background."""

import functools

import bw2calc as bc
from bw_graph_tools import GraphTraversalSettings, NewNodeEachVisitGraphTraversal

from bwbench import DIRECT_RTOL, bafu, check, first_time, heating, knob
from bwbench.asv import classes
from bwbench.bench import UNCHECKED, BenchSetup, NotApplicable, bench
from bwbench.synth import System, profile_version, system


@functools.cache
def background() -> tuple[System, dict[str, int]]:
    """BAFU with the heating factors, and the matrix index of each process the foreground names."""
    s = heating.corrected_system(system("bafu"))
    return s, heating.locate(bafu.archive(), heating.NAMES, s.ids)


@bench(
    {"size": knob("sizes", "smoke"), "option": list(heating.OPTIONS), "max_calc": [2, 100]},
    asv="HeatingTraversal",
    fresh_solver=False,
    version=f"{profile_version()}-heating{heating.VERSION}",
    timeout=900,
)
def traverse_heating(size: str, option: str, max_calc: int) -> BenchSetup:
    if size != "bafu":
        raise NotApplicable("the heating foreground requires BWBENCH_SIZES=bafu")
    s, at = background()
    fg = heating.foreground(s, at, **heating.DEFAULTS)
    demand = {fg.id(heating.OPTIONS[option]): 1.0}
    inventory, methods, _, _ = s.packages()
    lca = bc.LCA(demand, data_objs=[inventory, heating.datapackage(fg), methods[0]])
    lca.lci()
    lca.lcia()
    if first_time("traverse_heating", option):  # the same score every sample
        check(lca.score, heating.reference(s, fg, [demand])[0][0], DIRECT_RTOL, "heating traversal score")
    settings = GraphTraversalSettings(max_calc=max_calc, cutoff=1e-3)

    def run() -> NewNodeEachVisitGraphTraversal:
        traversal = NewNodeEachVisitGraphTraversal(lca, settings)
        traversal.traverse()
        return traversal

    return run, UNCHECKED


classes(__name__)
