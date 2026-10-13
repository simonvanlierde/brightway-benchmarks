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

from bwbench.synth import GENERATOR_VERSION, SIZES, System, as_bw2data, generate, method_name  # noqa: E402


def fresh_project(size: str) -> tuple[dict, System]:
    """A new project holding the biosphere and the methods; returns the technosphere data."""
    bd.projects.set_current(f"write-{uuid.uuid4().hex[:8]}")
    system = generate(SIZES[size])
    bio, tech, cfs = as_bw2data(system)
    bd.Database("bio").write(bio)
    for i, cf in enumerate(cfs):
        bd.Method(method_name(i)).write(cf)
    return tech, system


class DatabaseWrite:
    version = GENERATOR_VERSION
    params = (knob("write_sizes", "smoke"),)
    param_names = ["size"]
    number = 1
    repeat = (1, 5, 1200)
    timeout = 1800

    def setup_cache(self) -> float:
        """Check once per environment that a written database gives the reference score."""
        tech, system = fresh_project("smoke")
        ref = system.reference_scores(1)[0][0]
        bd.Database("synth").write(tech)
        fu, data_objs, _ = bd.prepare_lca_inputs({bd.get_node(database="synth", code="p0"): 1}, method=method_name(0))
        lca = bc.LCA(fu, data_objs=data_objs)
        lca.lci()
        lca.lcia()
        err = check(lca.score, ref, BW2DATA_RTOL, f"bw2data {bd.__version__} score")
        bd.projects.delete_project(delete_dir=True)
        return err

    def setup(self, err: float, size: str) -> None:
        self.tech, _ = fresh_project(size)

    def teardown(self, err: float, size: str) -> None:
        bd.projects.delete_project(delete_dir=True)

    def time_write(self, err: float, size: str) -> None:
        bd.Database("synth").write(self.tech)

    def track_score_error(self, err: float, size: str) -> float:
        return err
