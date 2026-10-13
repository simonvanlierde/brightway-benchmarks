"""bw2data: ``Database.write`` of a synthetic technosphere.

The history includes 106d627 (#268, raw SQLite ``executemany`` for bulk inserts,
merged 2026-05-13) and 646849c (#270, 2026-05-14), whose squash commit put peewee's
``insert_many`` back. Release 4.7 contains both, so it ships without #268's speed-up,
though its changelog lists #268. The step between those two points is what the
removal cost.
"""

import uuid

from bwbench import BW2DATA_RTOL, check, knob, temporary_brightway_dir

temporary_brightway_dir()

import bw2calc as bc  # noqa: E402
import bw2data as bd  # noqa: E402
import numpy as np  # noqa: E402
from scipy import sparse  # noqa: E402

from bwbench.synth import System, method_name, neumann, profile_version, system  # noqa: E402

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


class DatabaseWrite:
    version = profile_version(WRITE_SIZES)
    params = (WRITE_SIZES,)
    param_names = ["size"]
    number = 1
    repeat = (1, 5, 1200)
    timeout = 1800

    def setup(self, size: str) -> None:
        self.tech, self.system = fresh_project(size)

    def teardown(self, size: str) -> None:
        bd.projects.delete_project(delete_dir=True)

    def time_write(self, size: str) -> None:
        bd.Database("synth").write(self.tech)

    def track_score_error(self, size: str) -> float:
        """Write the database, then check at this size that it gives the reference score.

        bw2calc only loads the matrices: the solve is a Neumann series, which needs no
        factorization (SuperLU takes a minute or more at the ecoinvent size).
        """
        bd.Database("synth").write(self.tech)
        fu, data_objs, _ = bd.prepare_lca_inputs({bd.get_node(database="synth", code="p0"): 1}, method=method_name(0))
        lca = bc.LCA(fu, data_objs=data_objs)
        lca.load_lci_data()
        lca.build_demand_array()
        lca.load_lcia_data()
        a = lca.technosphere_matrix
        # bw2data numbers products by database id, so put the units in the matrix's order.
        ids = {node["code"]: node.id for node in bd.Database("synth")}
        scale = np.empty(a.shape[0])
        for i, unit in enumerate(self.system.scale):
            scale[lca.dicts.product[ids[f"p{i}"]]] = unit
        supply = neumann(sparse.identity(a.shape[0], format="csr") - a, lca.demand_array, scale=scale)
        score = float((lca.characterization_matrix @ lca.biosphere_matrix @ supply).sum())
        return check(score, self.system.reference[0][0], BW2DATA_RTOL, f"bw2data {bd.__version__} score")
