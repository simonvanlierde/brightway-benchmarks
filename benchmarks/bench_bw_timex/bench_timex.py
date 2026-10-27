"""bw_timex: ``TimexLCA.lci()`` as the timeline grows.

PR #244 writes the timeline's matrix changes as one vector per matrix instead of one
resource per entry (1.51 s to 0.36 s). Here ``consumers`` foreground processes each buy
a background product spread over ``steps`` years, so the timeline has about
``consumers * steps`` rows. The 2020 and 2030 backgrounds are the same synthetic
system, so the time-explicit static score must equal the plain LCA score.
"""

import contextlib
from collections.abc import Iterator
from datetime import datetime

from bwbench import DIRECT_RTOL, check, knob, temporary_brightway_dir

temporary_brightway_dir()

import bw2calc as bc  # noqa: E402
import bw2data as bd  # noqa: E402
import numpy as np  # noqa: E402
from bw_temporalis import TemporalDistribution  # noqa: E402
from bw_timex import TimexLCA  # noqa: E402

from bwbench.asv import classes  # noqa: E402
from bwbench.bench import BenchSetup, bench  # noqa: E402
from bwbench.synth import method_name, system  # noqa: E402

DATES = {"bg_2020": datetime(2020, 1, 1), "bg_2030": datetime(2030, 1, 1), "foreground": "dynamic"}
CONSUMERS = 10
TIMEX_SIZES = knob("timex_sizes", "smoke")


def build_project(size: str, steps: int) -> None:
    bd.projects.set_current(f"timex-{size}-{steps}")
    synthetic = system(size)
    bio, _, cfs = synthetic.bw2data()
    bd.Database("bio").write(bio)
    bd.Method(method_name(0)).write(cfs[0])
    for db in ("bg_2020", "bg_2030"):
        bd.Database(db).write(synthetic.bw2data(db=db)[1])
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


@bench(
    {"size": TIMEX_SIZES, "steps": knob("steps", "5,20", int)},
    error="static_score_error",
    asv="TimelineLCI",
    timeout=1800,
    repeat=(1, 5, 600),
)
def lci(size: str, steps: int) -> Iterator[BenchSetup]:
    build_project(size, steps)
    fu = bd.get_node(database="foreground", code="fu")
    tlca = TimexLCA({fu.key: 1}, method_name(0), DATES)
    tlca.build_timeline(starting_datetime="2024-01-01")

    def static_score_error(_: None) -> float:
        tlca.static_lcia()
        lca = bc.LCA({fu: 1}, method=method_name(0))
        lca.lci()
        lca.lcia()
        return check(tlca.static_score, lca.score, DIRECT_RTOL, "timex static score")

    yield tlca.lci, static_score_error
    # NOTE: on Windows the timeline's datapackage zips are still open here, so the folder cannot
    # go. bw2data has already dropped the project by then, and the folder sits in a temporary
    # Brightway dir, so leaving it is harmless.
    with contextlib.suppress(PermissionError):
        bd.projects.delete_project(delete_dir=True)


classes(__name__)
