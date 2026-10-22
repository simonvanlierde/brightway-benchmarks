"""bw2data: ``Database.write`` of a synthetic technosphere.

The history includes 106d627 (#268, raw SQLite ``executemany`` for bulk inserts,
merged 2026-05-13) and 646849c (#270, 2026-05-14), whose squash commit put peewee's
``insert_many`` back. Release 4.7 contains both, so it ships without #268's speed-up,
though its changelog lists #268. The step between those two points is what the
removal cost.
"""

import uuid
from collections.abc import Iterator

from bwbench import BW2DATA_RTOL, check, knob, temporary_brightway_dir

temporary_brightway_dir()

import bw2calc as bc  # noqa: E402
import bw2data as bd  # noqa: E402
import numpy as np  # noqa: E402

from bwbench.asv import classes  # noqa: E402
from bwbench.bench import BenchSetup, bench  # noqa: E402
from bwbench.synth import System, method_name, neumann_score, system  # noqa: E402

WRITE_SIZES = knob("write_sizes", "smoke")


def fresh_project(size: str) -> tuple[dict, System]:
    """A new project holding the biosphere and the methods; returns the technosphere data."""
    bd.projects.set_current(f"write-{uuid.uuid4().hex[:8]}")
    synthetic = system(size)
    bio, tech, cfs = synthetic.bw2data()
    bd.Database("bio").write(bio)
    for i, cf in enumerate(cfs):
        bd.Method(method_name(i)).write(cf)
    return tech, synthetic


def score_error(synthetic: System) -> float:
    """Check that the written database gives the reference score.

    bw2calc only loads the matrices: the solve is a Neumann series, which needs no
    factorization (SuperLU takes a minute or more at the ecoinvent size).
    """
    node = bd.get_node(database="synth", code="p0")
    fu, data_objs, _ = bd.prepare_lca_inputs({node: 1}, method=method_name(0))
    lca = bc.LCA(fu, data_objs=data_objs)
    lca.load_lci_data()
    lca.build_demand_array()
    lca.load_lcia_data()
    # bw2data numbers products by database id, so put the units in the matrix's order.
    ids = {n["code"]: n.id for n in bd.Database("synth")}
    order = [lca.dicts.product[ids[f"p{i}"]] for i in range(synthetic.profile.products)]
    scale = np.empty(len(order))
    scale[order] = synthetic.scale
    return check(neumann_score(lca, scale), synthetic.reference[0][0], BW2DATA_RTOL, f"bw2data {bd.__version__} score")


@bench({"size": WRITE_SIZES}, error="score_error", asv="DatabaseWrite", peakmem=True, timeout=1800, repeat=(1, 5, 1200))
def write(size: str) -> Iterator[BenchSetup]:
    tech, synthetic = fresh_project(size)
    yield lambda: bd.Database("synth").write(tech), lambda _: score_error(synthetic)
    bd.projects.delete_project(delete_dir=True)


classes(__name__)
