"""bw_timex: ``TimexLCA.lci()`` as the timeline grows.

PR #244 writes the timeline's matrix changes as one vector per matrix instead of one
resource per entry (1.51 s to 0.36 s). Here ``consumers`` foreground processes each buy
a background product spread over ``steps`` years, so the timeline has about
``consumers * steps`` rows. The 2020 and 2030 backgrounds are the same synthetic
system, so the time-explicit static score must equal the plain LCA score.
"""

from datetime import datetime

from bwbench import knob, temporary_brightway_dir

temporary_brightway_dir()

import bw2calc as bc  # noqa: E402
import bw2data as bd  # noqa: E402
import numpy as np  # noqa: E402
from bw_temporalis import TemporalDistribution  # noqa: E402
from bw_timex import TimexLCA  # noqa: E402

from bwbench.synth import SIZES, as_bw2data, generate, method_name  # noqa: E402

DATES = {"bg_2020": datetime(2020, 1, 1), "bg_2030": datetime(2030, 1, 1), "foreground": "dynamic"}
CONSUMERS = 10


def build_project(size: str, steps: int) -> None:
    bd.projects.set_current(f"timex-{size}-{steps}")
    system = generate(SIZES[size])
    bio, _, cfs = as_bw2data(system)
    bd.Database("bio").write(bio)
    bd.Method(method_name(0)).write(cfs[0])
    for db in ("bg_2020", "bg_2030"):
        bd.Database(db).write(as_bw2data(system, db=db)[1])
    td = TemporalDistribution(date=np.arange(-steps, 0).astype("timedelta64[Y]"), amount=np.full(steps, 1 / steps))
    fg = {
        ("foreground", "fu"): {
            "name": "fu",
            "unit": "unit",
            "location": "GLO",
            "exchanges": [{"input": ("foreground", "fu"), "amount": 1, "type": "production"}]
            + [{"input": ("foreground", f"c{i}"), "amount": 1, "type": "technosphere"} for i in range(CONSUMERS)],
        }
    }
    for i in range(CONSUMERS):
        fg["foreground", f"c{i}"] = {
            "name": f"c{i}",
            "unit": "unit",
            "location": "GLO",
            "exchanges": [
                {"input": ("foreground", f"c{i}"), "amount": 1, "type": "production"},
                {"input": ("bg_2020", f"p{i}"), "amount": 1, "type": "technosphere", "temporal_distribution": td},
            ],
        }
    bd.Database("foreground").write(fg)


class TimelineLCI:
    params = (knob("timex_sizes", "smoke"), [int(x) for x in knob("steps", "5,20")])
    param_names = ["size", "steps"]
    number = 1
    repeat = (1, 5, 600)
    timeout = 1800

    def setup(self, size: str, steps: int) -> None:
        build_project(size, steps)
        self.fu = bd.get_node(database="foreground", code="fu")
        self.tlca = TimexLCA({self.fu.key: 1}, method_name(0), DATES)
        self.tlca.build_timeline(starting_datetime="2024-01-01")

    def teardown(self, size: str, steps: int) -> None:
        bd.projects.delete_project(delete_dir=True)

    def time_lci(self, size: str, steps: int) -> None:
        self.tlca.lci()

    def track_static_score_error(self, size: str, steps: int) -> float:
        self.tlca.lci()
        self.tlca.static_lcia()
        lca = bc.LCA({self.fu: 1}, method=method_name(0))
        lca.lci()
        lca.lcia()
        err = abs(self.tlca.static_score - lca.score) / abs(lca.score)
        if err > 1e-9:
            msg = f"timex static score {self.tlca.static_score} vs LCA {lca.score}"
            raise AssertionError(msg)
        return err
