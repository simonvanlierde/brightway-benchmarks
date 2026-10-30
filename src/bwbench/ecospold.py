"""A synthetic system written as an ecoSpold2 release, for timing bw2io's import without an ecoinvent licence.

``write_ecospold(system, folder, flows)`` writes ``folder/datasets/``, one ``.spold`` file per
product, with the elements and attributes bw2io's ``Ecospold2DataExtractor`` reads (bw2io
0.9.17). There is no ``MasterData/``: bw2io then skips the product descriptions it would add
from there, and the biosphere comes from elsewhere. Each file is as heavy as an ecoinvent 3.12
one, from the release's means in ``HEAVY``; docs/method.md says how.

Each product has a fixed activity and product UUID. Technosphere inputs carry an
``activityLinkId``, so ``link_internal_technosphere_by_composite_code`` links all of them.
Elementary exchanges link only by UUID (``link_biosphere_by_flow_uuid``), so flow ``j`` takes
``flows[j]``: the ids of the biosphere database the import links against, such as the
``biosphere3`` that ``bw2io.create_default_biosphere3()`` writes.
"""

from __future__ import annotations

import collections
import json
import math
import uuid
from typing import TYPE_CHECKING

import numpy as np

from bwbench.synth import PROFILES_DIR

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    from bwbench.synth import System

NAMESPACE = uuid.UUID("5b0c0d47-6f0e-4b5e-9d0c-3e1f7a1b2c3d")  # any fixed UUID: the same ids on every run
# Means of ecoinvent 3.12's files. The extra content adds weight but changes no matrix amount.
HEAVY = json.loads((PROFILES_DIR / "ecoinvent-3.12-cutoff.json").read_text())["ecospold"]
REVIEW_CHARS = 15757  # sized so a dataset at `ecoinvent` size averages HEAVY["bytes"]; real reviews are shorter
HEAD = """<?xml version="1.0" encoding="UTF-8"?>
<ecoSpold xmlns="http://www.EcoInvent.org/EcoSpold02">
<activityDataset>
<activityDescription>
<activity id="{activity}"><activityName>process {i}</activityName><generalComment>{general}</generalComment></activity>
<geography><shortname>GLO</shortname></geography>
<technology/>
<timePeriod startDate="2026-01-01" endDate="2026-12-31" isDataValidForEntirePeriod="true"/>
</activityDescription>
<flowData>
"""
PRODUCT = """<intermediateExchange intermediateExchangeId="{product}" \
unitId="487df68b-4994-4027-8fdc-a4dc298257b7" amount="{amount!r}">\
<name xml:lang="en">product {i}</name>\
<unitName xml:lang="en">kg</unitName>{extra}<outputGroup>0</outputGroup></intermediateExchange>
"""
INPUT = """<intermediateExchange intermediateExchangeId="{product}" \
unitId="487df68b-4994-4027-8fdc-a4dc298257b7" activityLinkId="{activity}" amount="{amount!r}">\
<name xml:lang="en">product {i}</name>\
<unitName xml:lang="en">kg</unitName>{extra}<inputGroup>5</inputGroup></intermediateExchange>
"""
EMISSION = """<elementaryExchange elementaryExchangeId="{flow}" \
unitId="487df68b-4994-4027-8fdc-a4dc298257b7" amount="{amount!r}">\
<name xml:lang="en">flow {j}</name>\
<unitName xml:lang="en">kg</unitName>{extra}<outputGroup>4</outputGroup></elementaryExchange>
"""


def _text(chars: int) -> str:
    return ("synthetic text " * (chars // 15 + 1))[:chars]


COMMENT = {kind: f'<comment xml:lang="en">{_text(round(c))}</comment>' for kind, (_, c) in HEAVY["comments"].items()}
GENERAL = '<text index="{k}">' + _text(round(HEAVY["general_comment"][1])) + "</text>"
REVIEW = "<review><otherDetails>" + _text(REVIEW_CHARS) + "</otherDetails></review>"
UNCERTAINTY = """<uncertainty><lognormal meanValue="{amount!r}" mu="{mu!r}" variance="0.04" \
varianceWithPedigreeUncertainty="0.0625"/><pedigreeMatrix reliability="2" completeness="3" temporalCorrelation="1" \
geographicalCorrelation="2" furtherTechnologyCorrelation="1"/>{comment}</uncertainty>"""
PROPERTY = """<property propertyId="{id}" amount="1.0" unitId="577e1a2c-4c2b-4d1e-9a3f-ff0d8f8b6a10" \
isDefiningValue="true"><name xml:lang="en">property {k}</name>\
<unitName xml:lang="en">dimensionless</unitName>{comment}</property>"""
PARAMETER = """<parameter parameterId="{id}" variableName="p{k}" amount="1.0"><name xml:lang="en">parameter {k}</name>\
<unitName xml:lang="en">dimensionless</unitName>{comment}</parameter>
"""
TAIL = """</flowData>
<modellingAndValidation>{reviews}</modellingAndValidation>
<administrativeInformation><dataEntryBy/><dataGeneratorAndPublication/></administrativeInformation>
</activityDataset>
</ecoSpold>
"""


def _count(mean: float, i: int) -> int:
    """Dataset ``i``'s share of a per-dataset mean: whole numbers that average ``mean`` over the datasets."""
    return int(mean + i * 0.6180339887 % 1)


def _extras(i: int, exchanges: list[tuple[str, float]]) -> list[str]:
    """Dataset ``i``'s properties, uncertainties and comments, one string per (kind, amount) exchange.

    Each exchange carries at most one comment of its kind, up to the release's mean count.
    """
    n = len(exchanges)
    props, uncertain = _count(HEAVY["properties"], i), _count(HEAVY["lognormal_uncertainties"], i)
    want = {kind: _count(count, i) for kind, (count, _) in HEAVY["comments"].items()}
    had: collections.Counter[str] = collections.Counter()

    def comment(kind: str) -> str:
        had[kind] += 1
        return COMMENT[kind] if had[kind] <= want[kind] else ""

    out = []
    for e, (kind, amount) in enumerate(exchanges):
        parts = [comment(kind)]
        if e < uncertain and amount:  # bw2io's set_lognormal_loc_value takes log(|amount|)
            parts.append(UNCERTAINTY.format(amount=amount, mu=math.log(abs(amount)), comment=comment("uncertainty")))
        parts += [PROPERTY.format(id=PROPERTY_IDS[k], k=k, comment=comment("property")) for k in range(e, props, n)]
        out.append("".join(parts))
    return out


PROPERTY_IDS = [uuid.uuid5(NAMESPACE, f"property {k}") for k in range(int(HEAVY["properties"]) + 1)]


def write_ecospold(system: System, folder: Path, flows: Sequence[str]) -> int:
    """Write ``system`` as an ecoSpold2 release in ``folder`` and return the number of exchanges written.

    ``flows[j]`` is the UUID of biosphere flow ``j``; the first ``system.profile.flows`` hold the
    system's own exchanges, with its exact amounts, so on those flows the imported matrices equal
    its own. The flows past them pad each dataset to ecoinvent's mean count of elementary
    exchanges, with amounts under 1e-6, so an LCIA method must not characterise them.
    """
    if len(flows) < system.profile.flows:
        msg = f"the system has {system.profile.flows} flows, but only {len(flows)} UUIDs were given"
        raise ValueError(msg)
    n, off, spare = system.profile.products, system.flow_offset, len(flows) - system.profile.flows
    activity = [uuid.uuid5(NAMESPACE, f"activity {i}") for i in range(n)]
    product = [uuid.uuid5(NAMESPACE, f"product {i}") for i in range(n)]
    tech = sorted(zip(system.tech_cols.tolist(), system.tech_rows.tolist(), system.tech_data.tolist(), strict=True))
    bio = sorted(zip(system.bio_cols.tolist(), system.bio_rows.tolist(), system.bio_data.tolist(), strict=True))
    tech_at = np.searchsorted([c for c, *_ in tech], np.arange(n + 1)).tolist()
    bio_at = np.searchsorted([c for c, *_ in bio], np.arange(n + 1)).tolist()
    out = folder / "datasets"
    out.mkdir(parents=True)
    written = 0
    for i in range(n):
        # (kind, template, fields, amount), the production exchange first
        exchanges = []
        for _, r, amount in tech[tech_at[i] : tech_at[i + 1]]:
            if r == i:
                exchanges.insert(0, ("intermediateExchange", PRODUCT, {"product": product[i], "i": i}, amount))
            else:
                fields = {"product": product[r], "activity": activity[r], "i": r}
                exchanges.append(("intermediateExchange", INPUT, fields, amount))
        emissions = [(r - off, a) for _, r, a in bio[bio_at[i] : bio_at[i + 1]]]
        pad = min(max(_count(HEAVY["elementary_exchanges"], i) - len(emissions), 0), spare)
        emissions += [(system.profile.flows + (i * 31 + k) % spare, 1e-9 * (k + 1)) for k in range(pad)]
        exchanges += [("elementaryExchange", EMISSION, {"flow": flows[j], "j": j}, a) for j, a in emissions]
        extras = _extras(i, [(k, a) for k, _, _, a in exchanges])
        general = "".join(GENERAL.format(k=k) for k in range(_count(HEAVY["general_comment"][0], i)))
        parts = [HEAD.format(activity=activity[i], i=i, general=general)]
        parts += [t.format(amount=a, extra=x, **f) for (_, t, f, a), x in zip(exchanges, extras, strict=True)]
        parts += [
            PARAMETER.format(
                id=uuid.uuid5(NAMESPACE, f"parameter {i} {k}"),
                k=k,
                comment=COMMENT["parameter"] if k < _count(HEAVY["comments"]["parameter"][0], i) else "",
            )
            for k in range(_count(HEAVY["parameters"], i))
        ]
        parts.append(TAIL.format(reviews=REVIEW * _count(HEAVY["review_details"][0], i)))
        (out / f"{activity[i]}_{product[i]}.spold").write_text("".join(parts), encoding="utf-8")
        written += len(exchanges)
    return written
