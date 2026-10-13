"""Structural statistics of a licensed ecoinvent release, for calibrating the generator.

    uv run scripts/measure_stats.py ~/ecoinvent/3.12-cutoff src/bwbench/profiles/ecoinvent-3.12-cutoff.json

Reads the linked ecospold2 datasets (one file per activity and reference product) and
writes only what ``bwbench.synth.measure`` returns: counts and distributions, never a
dataset, a name or an amount. Publishing these aggregates is allowed under the ecoinvent
EULA (checked with the licence holder, 2026-10-13). The datasets themselves stay on the
machine that holds the licence.
"""

# First, so the BLAS thread pin lands before numpy loads (bwbench warns otherwise).
import bwbench  # noqa: F401, I001
import json
import os
import sys
import xml.etree.ElementTree as ET
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path

import numpy as np
from scipy import sparse

from bwbench.synth import measure

NS = "{http://www.EcoInvent.org/EcoSpold02}"
REFERENCE_PRODUCT = "0"  # ecospold2 outputGroup of the reference product


def read(path: Path) -> tuple:
    """(product key, reference amount, location, ISIC division, [(supplier key, amount)])."""
    root = ET.parse(path).getroot()  # noqa: S314 - the licensee's own downloaded release
    activity = root.find(f".//{NS}activity").get("id")
    location = root.find(f".//{NS}geography/{NS}shortname").text
    isic = ""
    for c in root.iter(f"{NS}classification"):
        if c.findtext(f"{NS}classificationSystem", "").startswith("ISIC"):
            isic = c.findtext(f"{NS}classificationValue", "")[:2]
    ref, inputs = None, []
    for ex in root.iter(f"{NS}intermediateExchange"):
        amount = float(ex.get("amount"))
        if ex.findtext(f"{NS}outputGroup") == REFERENCE_PRODUCT:
            ref = ((activity, ex.get("intermediateExchangeId")), amount)
        elif ex.get("activityLinkId") and amount != 0:
            inputs.append(((ex.get("activityLinkId"), ex.get("intermediateExchangeId")), amount))
    if ref is None:
        msg = f"{path.name}: no reference product"
        raise ValueError(msg)
    return ref[0], ref[1], location, isic, inputs


def main(folder: Path, out: Path) -> None:
    """Parse every dataset in ``folder/datasets`` and write the statistics to ``out``."""
    files = sorted((folder / "datasets").glob("*.spold"))
    with ProcessPoolExecutor(max_workers=min(8, os.cpu_count() or 1)) as pool:
        records = list(pool.map(read, files, chunksize=200))

    index = {key: i for i, (key, *_) in enumerate(records)}
    if len(index) != len(records):
        msg = "two datasets share a reference product"
        raise ValueError(msg)
    rows, cols, data = [], [], []
    unlinked = self_inputs = 0
    for j, (_key, ref, *_, inputs) in enumerate(records):
        rows.append(j)
        cols.append(j)
        data.append(ref)
        for supplier, amount in inputs:
            i = index.get(supplier)
            if i is None:
                unlinked += 1
                continue
            self_inputs += i == j  # lands on the diagonal: bw2calc solves on net production
            rows.append(i)
            cols.append(j)
            data.append(-amount)  # bw2calc's sign: inputs negative, production positive
    n = len(records)
    a = sparse.csc_matrix((np.array(data), (np.array(rows), np.array(cols))), shape=(n, n))
    a.sum_duplicates()

    stats = measure(a, locations=[r[2] for r in records], sectors=[r[3] for r in records])
    result = {
        "source": f"ecoinvent {folder.name} (ecospold2), aggregates only",
        "measured": datetime.now(UTC).date().isoformat(),
        "datasets": n,
        "unlinked_inputs": unlinked,
        "self_inputs": self_inputs,
        "versions": {"numpy": version("numpy"), "scipy": version("scipy")},
        "stats": asdict(stats),
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main(Path(sys.argv[1]).expanduser(), Path(sys.argv[2]))
