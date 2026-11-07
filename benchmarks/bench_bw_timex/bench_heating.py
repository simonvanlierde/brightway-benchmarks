"""Heating spread over twenty years, with an unchanged BAFU background.

This isolates timeline expansion; it makes no forecast of future electricity or gas.
The complete per-heat inventory, including allocated equipment, is spread evenly by year.
This is an explicit benchmark assumption, not a separate installation-and-operation schedule.
"""

import contextlib
from collections.abc import Iterator
from datetime import datetime

from bwbench import DIRECT_RTOL, bafu, check, heating, knob, temporary_brightway_dir

temporary_brightway_dir()

import bw2data as bd  # noqa: E402
import numpy as np  # noqa: E402
from bw_temporalis import TemporalDistribution  # noqa: E402
from bw_timex import TimexLCA  # noqa: E402
from scipy import sparse  # noqa: E402

from bwbench.asv import classes  # noqa: E402
from bwbench.bench import BenchSetup, NotApplicable, bench  # noqa: E402
from bwbench.synth import method_name, neumann_score, profile_version, system  # noqa: E402


@bench(
    {"size": knob("timex_sizes", "smoke"), "option": list(heating.OPTIONS)},
    asv="HeatingTimeline",
    error="static_score_error",
    version=f"{profile_version()}-heating{heating.VERSION}",
    timeout=1800,
    repeat=(1, 5, 600),
)
def heating_lci(size: str, option: str) -> Iterator[BenchSetup]:
    if size != "bafu":
        raise NotApplicable("the heating foreground requires BWBENCH_TIMEX_SIZES=bafu")
    bd.projects.set_current(f"heating-timex-{option}")
    s = heating.corrected_system(system(size))
    fg = heating.foreground(s, heating.locate(bafu.archive(), heating.NAMES, s.ids), **heating.DEFAULTS)
    bio, background, methods = s.bw2data(db="background")
    bd.Database("bio").write(bio)
    bd.Database("background").write(background)
    bd.Method(method_name(0)).write(methods[0])
    records = heating.bw2data(s, fg)
    node = heating.OPTIONS[option]
    td = TemporalDistribution(
        date=np.arange(heating.YEARS).astype("timedelta64[Y]"), amount=np.full(heating.YEARS, 1 / heating.YEARS)
    )
    for exchange in records["foreground", str(node)]["exchanges"]:
        if exchange["type"] == "technosphere":
            exchange["temporal_distribution"] = td
    bd.Database("foreground").write(records)
    fu = bd.get_node(database="foreground", code=str(node))
    tlca = TimexLCA({fu.key: 1}, method_name(0), {"foreground": "dynamic", "background": datetime(2025, 1, 1)})
    tlca.build_timeline(starting_datetime="2025-01-01", cutoff=1e-12)
    # bw2data changes precision when processing exchanges; check the actual stored matrices.
    base = tlca.base_lca
    scale = np.ones(base.technosphere_matrix.shape[0])
    inputs = sparse.identity(scale.size, format="csr") - base.technosphere_matrix
    positions = [
        base.dicts.product[bd.get_node(database="foreground", code=str(i)).id] for i in range(len(heating.NODES))
    ]
    scale[positions] = 0.5 / np.maximum(1.0, abs(inputs).max(axis=0).toarray().ravel()[positions])
    expected = neumann_score(base, scale)

    def static_score_error(_: None) -> float:
        tlca.static_lcia()
        return check(tlca.static_score, expected, DIRECT_RTOL, "heating timex static score")

    yield tlca.lci, static_score_error
    with contextlib.suppress(PermissionError):
        bd.projects.delete_project(delete_dir=True)


classes(__name__)
