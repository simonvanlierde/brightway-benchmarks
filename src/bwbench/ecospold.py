"""A synthetic system written as an ecoSpold2 release, for timing bw2io's import without an ecoinvent licence.

``write_ecospold(system, folder, flows)`` writes ``folder/datasets/``, one ``.spold`` file per
product, with the elements and attributes bw2io's ``Ecospold2DataExtractor`` reads (bw2io
0.9.17) and nothing more. There is no ``MasterData/``: bw2io then skips the product
descriptions it would add from there, and the biosphere comes from elsewhere.

Each product has a fixed activity and product UUID. Technosphere inputs carry an
``activityLinkId``, so ``link_internal_technosphere_by_composite_code`` links all of them.
Elementary exchanges link only by UUID (``link_biosphere_by_flow_uuid``), so flow ``j`` takes
``flows[j]``: the ids of the biosphere database the import links against, such as the
``biosphere3`` that ``bw2io.create_default_biosphere3()`` writes.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    from bwbench.synth import System

NAMESPACE = uuid.UUID("5b0c0d47-6f0e-4b5e-9d0c-3e1f7a1b2c3d")  # any fixed UUID: the same ids on every run
HEAD = """<?xml version="1.0" encoding="UTF-8"?>
<ecoSpold xmlns="http://www.EcoInvent.org/EcoSpold02">
<activityDataset>
<activityDescription>
<activity id="{activity}"><activityName>process {i}</activityName></activity>
<geography><shortname>GLO</shortname></geography>
<technology/>
<timePeriod startDate="2026-01-01" endDate="2026-12-31" isDataValidForEntirePeriod="true"/>
</activityDescription>
<flowData>
<intermediateExchange intermediateExchangeId="{product}" amount="{amount!r}">\
<name>product {i}</name><unitName>kg</unitName><outputGroup>0</outputGroup></intermediateExchange>
"""
INPUT = """<intermediateExchange intermediateExchangeId="{product}" activityLinkId="{activity}" amount="{amount!r}">\
<name>product {i}</name><unitName>kg</unitName><inputGroup>5</inputGroup></intermediateExchange>
"""
EMISSION = """<elementaryExchange elementaryExchangeId="{flow}" amount="{amount!r}">\
<name>flow {j}</name><unitName>kg</unitName><outputGroup>4</outputGroup></elementaryExchange>
"""
TAIL = """</flowData>
<administrativeInformation><dataEntryBy/><dataGeneratorAndPublication/></administrativeInformation>
</activityDataset>
</ecoSpold>
"""


def write_ecospold(system: System, folder: Path, flows: Sequence[str]) -> Path:
    """Write ``system`` as an ecoSpold2 release in ``folder`` and return ``folder``.

    ``flows[j]`` is the UUID of biosphere flow ``j``; the first ``system.profile.flows`` are used.
    The files hold the system's exact amounts, so the imported matrices equal its own.
    """
    if len(flows) < system.profile.flows:
        msg = f"the system has {system.profile.flows} flows, but only {len(flows)} UUIDs were given"
        raise ValueError(msg)
    n, off = system.profile.products, system.flow_offset
    activity = [uuid.uuid5(NAMESPACE, f"activity {i}") for i in range(n)]
    product = [uuid.uuid5(NAMESPACE, f"product {i}") for i in range(n)]
    tech = sorted(zip(system.tech_cols.tolist(), system.tech_rows.tolist(), system.tech_data.tolist(), strict=True))
    bio = sorted(zip(system.bio_cols.tolist(), system.bio_rows.tolist(), system.bio_data.tolist(), strict=True))
    tech_at = np.searchsorted([c for c, *_ in tech], np.arange(n + 1)).tolist()
    bio_at = np.searchsorted([c for c, *_ in bio], np.arange(n + 1)).tolist()
    out = folder / "datasets"
    out.mkdir(parents=True)
    for i in range(n):
        parts = []
        for _, r, amount in tech[tech_at[i] : tech_at[i + 1]]:
            if r == i:  # the production exchange
                parts.insert(0, HEAD.format(activity=activity[i], product=product[i], amount=amount, i=i))
            else:
                parts.append(INPUT.format(product=product[r], activity=activity[r], amount=amount, i=r))
        parts += [
            EMISSION.format(flow=flows[r - off], amount=a, j=r - off) for _, r, a in bio[bio_at[i] : bio_at[i + 1]]
        ]
        parts.append(TAIL)
        (out / f"{activity[i]}_{product[i]}.spold").write_text("".join(parts), encoding="utf-8")
    return folder
