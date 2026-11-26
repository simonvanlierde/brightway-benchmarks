"""Heating spread over twenty years, with an unchanged BAFU background.

This isolates timeline expansion; it makes no forecast of future electricity or gas.
The complete per-heat inventory, including allocated equipment, is spread evenly by year.
This is an explicit benchmark assumption, not a separate installation-and-operation schedule.
"""

import re
from datetime import datetime
from importlib import metadata

from bwbench import (
    DIRECT_RTOL,
    assert_stamps_unchanged,
    check,
    first_time,
    heating,
    knob,
    stamps,
    temporary_brightway_dir,
)

temporary_brightway_dir()

import bw2data as bd  # noqa: E402
import numpy as np  # noqa: E402
from bw_temporalis import TemporalDistribution  # noqa: E402
from bw_timex import TimexLCA, clear_background_lci_cache  # noqa: E402
from scipy import sparse  # noqa: E402

from bwbench.asv import classes  # noqa: E402
from bwbench.bench import BenchSetup, NotApplicable, bench  # noqa: E402
from bwbench.matrices import method_name, neumann_score  # noqa: E402
from bwbench.synth import profile_version  # noqa: E402


@bench(
    {"size": knob("timex_sizes", "smoke"), "option": list(heating.OPTIONS)},
    asv="HeatingTimeline",
    error="static_score_error",
    version=f"{profile_version()}-heating{heating.VERSION}",
    timeout=1800,
    repeat=(1, 3, 180.0),
)
def heating_lci(size: str, option: str) -> BenchSetup:
    if size != "bafu":
        raise NotApplicable("the heating foreground requires BWBENCH_TIMEX_SIZES=bafu")
    # bw_timex < 1.2.1 passes a length-1 flip_array for every producer's biosphere flows, which
    # bw_processing 1.5+ rejects once a process has several (fixed in bw_timex e6406e5, issue #212).
    if tuple(int(n) for n in re.findall(r"\d+", metadata.version("bw_timex"))[:3]) < (1, 2, 1):  # 1.3.0rc1 too
        raise NotApplicable("bw_timex before 1.2.1 builds a mismatched biosphere flip_array (bw_timex #212)")
    bd.projects.set_current("heating-timex")
    s, at = heating.background()
    if first_time("heating background"):  # once per process; each sample writes only the foreground
        bio, records, methods = s.bw2data(db="background")
        bd.Database("bio").write(bio)
        bd.Database("background").write(records)
        bd.Method(method_name(0)).write(methods[0])
    clear_background_lci_cache()  # as in bench_timex: every sample is a first TimexLCA of its session
    modified = stamps("bio", "background")
    records = heating.bw2data(s, heating.foreground(s, at, **heating.DEFAULTS))
    node = heating.OPTIONS[option]
    td = TemporalDistribution(
        date=np.arange(heating.YEARS).astype("timedelta64[Y]"), amount=np.full(heating.YEARS, 1 / heating.YEARS)
    )
    for exchange in records["foreground", str(node)]["exchanges"]:
        if exchange["type"] == "technosphere":
            exchange["temporal_distribution"] = td
    bd.Database("foreground").write(records)  # a write replaces the last sample's
    fu = bd.get_node(database="foreground", code=str(node))
    tlca = TimexLCA({fu.key: 1}, method_name(0), {"foreground": "dynamic", "background": datetime(2025, 1, 1)})
    tlca.build_timeline(starting_datetime="2025-01-01", cutoff=1e-12)

    def static_score_error(_: None) -> float:
        assert_stamps_unchanged(modified)
        # bw2data changes precision when processing exchanges; check the actual stored matrices.
        base = tlca.base_lca
        scale = np.ones(base.technosphere_matrix.shape[0])
        inputs = sparse.identity(scale.size, format="csr") - base.technosphere_matrix
        positions = [
            base.dicts.product[bd.get_node(database="foreground", code=str(i)).id] for i in range(len(heating.NODES))
        ]
        scale[positions] = 0.5 / np.maximum(1.0, abs(inputs).max(axis=0).toarray().ravel()[positions])
        tlca.static_lcia()
        return check(tlca.static_score, neumann_score(base, scale), DIRECT_RTOL, "heating timex static score")

    return tlca.lci, static_score_error


classes(__name__)
