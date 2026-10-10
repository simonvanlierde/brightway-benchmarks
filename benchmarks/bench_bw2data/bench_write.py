"""bw2data: ``Database.write`` of a synthetic technosphere.

The history includes 106d627 (#268, raw SQLite ``executemany`` for bulk inserts,
merged 2026-05-13) and 646849c (#270, 2026-05-14), whose squash commit put peewee's
``insert_many`` back. Release 4.7 contains both, so it ships without #268's speed-up,
though its changelog lists #268. The step between those two points is what the
removal cost.
"""

import uuid

from bwbench import knob, temporary_brightway_dir

temporary_brightway_dir()

import bw2calc as bc  # noqa: E402
import bw2data as bd  # noqa: E402

from bwbench.synth import SIZES, as_bw2data, generate, method_name  # noqa: E402


def fresh_project(size: str) -> tuple[dict, list]:
    """A new project holding the biosphere and the methods; returns the technosphere data."""
    bd.projects.set_current(f"write-{uuid.uuid4().hex[:8]}")
    system = generate(SIZES[size])
    bio, tech, cfs = as_bw2data(system)
    bd.Database("bio").write(bio)
    for i, cf in enumerate(cfs):
        bd.Method(method_name(i)).write(cf)
    return tech, system.reference_scores()


class DatabaseWrite:
    params = (knob("write_sizes", "smoke"),)
    param_names = ["size"]
    number = 1
    repeat = (1, 5, 1200)
    timeout = 1800

    def setup_cache(self) -> float:
        """Check once per environment that a written database gives the reference score.

        The tolerance is 1e-6, not 1e-9: bw2data's processed arrays give a relative error
        near 3e-8 against the float64 reference (bw_processing #112 reports float32
        amounts moving scores by about 1e-7). ``track_score_error`` records it.
        """
        tech, refs = fresh_project("smoke")
        bd.Database("synth").write(tech)
        fu, data_objs, _ = bd.prepare_lca_inputs({bd.get_node(database="synth", code="p0"): 1}, method=method_name(0))
        lca = bc.LCA(fu, data_objs=data_objs)
        lca.lci()
        lca.lcia()
        err = abs(lca.score - refs[0]) / abs(refs[0])
        if err > 1e-6:
            msg = f"bw2data {bd.__version__}: score {lca.score} vs reference {refs[0]}"
            raise AssertionError(msg)
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
