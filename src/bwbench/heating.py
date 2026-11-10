"""A home-heating foreground on BAFU 2025: an air-water heat pump against a condensing gas boiler, in the Netherlands.

``foreground`` adds six nodes to the BAFU system, numbered after its flows:

- ``grid NL``: 1 kWh of BAFU's Dutch low-voltage grid, with ``renewable_share`` of it replaced
  by Dutch photovoltaics;
- ``heat pump``: a copy of BAFU's Swiss air-water heat pump, 1 MJ of heat, whose own Swiss
  electricity is replaced by ``1 / cop`` from ``grid NL``;
- ``burner`` and ``gas boiler``: copies of BAFU's condensing gas boiler (the burner and the heat
  it gives), burning Dutch gas, its auxiliary electricity from ``grid NL``;
- one ``20 years`` node per option, demanding ``heat_demand_kwh`` a year of heat for 20 years.

Only BAFU's process names appear here: its values are read from the archive at run time
(``bwbench.bafu``). Foreground assembly and reference solves need only numpy and scipy.
Reading the archive and writing datapackages need bw_processing, inside the benchmark container.
"""

from __future__ import annotations

import hashlib
import io
import json
import pickle
import sqlite3
import tarfile
import tempfile
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple

import numpy as np
from scipy import sparse

from bwbench.synth import neumann

if TYPE_CHECKING:
    from collections.abc import Mapping

    from numpy.typing import NDArray

    from bwbench.synth import System

# BAFU 2025 products, by their name and location as the archive's `product` column holds them.
HEAT_PUMP = "Heat, at heat pump, air-water, 7kW, CH electricity, in new building {CH}"
BOILER = "Heat, natural gas, at boiler condensing modulating 15kW {CH}"
BURNER = "Natural gas, burned in boiler condensing modulating 15kW {CH}"
GRID_CH = "Electricity, low voltage, at grid {CH}"  # the heat pump's electricity
GRID_ENTSOE = "Electricity, low voltage, production ENTSO-E, at grid {ENTSO-E}"  # the burner's
GAS_CH = "Natural gas, low pressure, at consumer {CH}"
GRID_NL = "Electricity, low voltage, at grid {NL}"
PV_NL = "Electricity, production mix photovoltaic, at plant {NL}"
GAS_NL = "Natural gas, low pressure, at consumer {NL}"
NAMES = (HEAT_PUMP, BOILER, BURNER, GRID_CH, GRID_ENTSOE, GAS_CH, GRID_NL, PV_NL, GAS_NL)

NODES = ("grid NL", "heat pump", "burner", "gas boiler", "heat pump, 20 years", "gas boiler, 20 years")
GRID, HP, BURNER_NODE, BOILER_NODE, HP_YEARS, BOILER_YEARS = range(len(NODES))
OPTIONS = {"heat pump": HP_YEARS, "gas boiler": BOILER_YEARS}
YEARS = 20
VERSION = "3"  # bump with any change to the foreground or the heating cases: it restarts their history
MJ_PER_KWH = 3.6
# These are illustrative benchmark assumptions, not measured Dutch averages.
# Staffell et al. (2012), doi:10.1039/C2EE22653G, review performance across systems and climates;
# a fixed seasonal COP of 3 represents one scenario, not their universal field-trial result.
# CBS's January 2026 energy bill reports gas consumption, not useful space heat:
# https://www.cbs.nl/nl-nl/longread/aanvullende-statistische-diensten/2026/de-energierekening-januari-2026
# 10,000 kWh/year is a round useful-heat assumption; no gas-to-heat conversion is calibrated here.
# renewable_share 0 uses BAFU's Dutch grid; 1 uses Dutch photovoltaics alone.
DEFAULTS = {"cop": 3.0, "heat_demand_kwh": 10_000.0, "renewable_share": 0.0}


class Foreground(NamedTuple):
    """The foreground's matrix entries, with bw2calc's sign convention, as ``System`` holds them.

    Node ``i`` of ``NODES`` has id ``base + i``; rows below ``base`` are BAFU's products and flows.
    """

    base: int
    tech_rows: NDArray[np.int64]
    tech_cols: NDArray[np.int64]
    tech_data: NDArray[np.float64]
    tech_flip: NDArray[np.bool_]
    bio_rows: NDArray[np.int64]
    bio_cols: NDArray[np.int64]
    bio_data: NDArray[np.float64]

    def id(self, node: int) -> int:
        """The matrix id of node ``node``."""
        return self.base + node


def locate(archive: Path, names: tuple[str, ...], ids: NDArray[np.int64]) -> dict[str, int]:
    """The matrix index of each product in ``names``, read from the project archive's SQLite database.

    ``ids`` is the archive's process id of each matrix index (``System.ids``). Raises
    ``ValueError`` for a name that is missing or not unique. The map is cached beside the archive.
    """
    cached = _derived(archive, "locate.json", names, ids)
    if cached.exists():
        return json.loads(cached.read_text())
    with tempfile.TemporaryDirectory() as tmp, tarfile.open(archive) as tar:
        member = next(m for m in tar.getmembers() if m.name.endswith("/lci/databases.db"))
        tar.extract(member, tmp, filter="data")
        con = sqlite3.connect(Path(tmp) / member.name)
        try:
            found = {
                n: [r[0] for r in con.execute("select id from activitydataset where product = ?", (n,))] for n in names
            }
        finally:
            con.close()
    at = {}
    for name, hits in found.items():
        if len(hits) != 1:
            msg = f"{len(hits)} processes make {name!r}, not one"
            raise ValueError(msg)
        i = int(np.searchsorted(ids, hits[0]))
        if i >= ids.size or ids[i] != hits[0]:
            msg = f"{name!r} is not in the matrix"
            raise ValueError(msg)
        at[name] = i
    _keep(cached, json.dumps(at).encode())
    return at


def _derived(archive: Path, what: str, *key: object) -> Path:
    """Where ``what``, derived from ``archive`` and ``key``, is cached: beside the archive.

    BAFU's values may not leave the machine, so what is derived from them stays where the
    archive is. The name holds a hash of the archive's SHA-256, ``VERSION`` and ``key``, so a
    new archive or a new heating version misses the old file.
    """
    from bwbench import useeio  # noqa: PLC0415 - as in corrected_system

    h = hashlib.sha256(f"{useeio.sha256_of(archive)} {VERSION}".encode())
    for k in key:
        h.update(k.tobytes() if isinstance(k, np.ndarray) else repr(k).encode())
    return archive.with_name(f"{archive.name}.{what.replace('.', f'-{h.hexdigest()[:16]}.')}")


def _keep(path: Path, data: bytes) -> None:
    """Write ``data`` to ``path`` through a rename, so no reader sees half a file. A read-only folder keeps nothing."""
    part = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=path.name, suffix=".part", delete=False) as f:
            part = Path(f.name)
            f.write(data)
        part.replace(path)
    except OSError:
        if part is not None:
            part.unlink(missing_ok=True)


def _inputs(col: int, pairs: list[tuple[int, float]]) -> tuple:
    rows, data = zip(*pairs, strict=True)
    return np.array(rows), np.full(len(rows), col), np.array(data, dtype=np.float64), np.ones(len(rows), dtype=bool)


def _copy(system: System, col: int, node: int, redirect: dict[int, tuple[int, float | None]]) -> tuple[tuple, tuple]:
    """Process ``col``'s inputs and emissions as node ``node``'s, its production left out.

    ``redirect`` moves the inputs of a product to another, with a new amount where one is given.
    """
    own = (system.tech_cols == col) & (system.tech_rows == col) & ~system.tech_flip
    if not np.allclose(system.tech_data[own], 1.0):
        msg = f"process {col} produces {system.tech_data[own]}, not 1: its inputs would need rescaling"
        raise ValueError(msg)
    keep = (system.tech_cols == col) & ~own
    rows, data = system.tech_rows[keep].copy(), system.tech_data[keep].copy()
    for old, (new, amount) in redirect.items():
        hit = rows == old
        if not hit.any() or (amount is not None and hit.sum() != 1):
            msg = f"process {col} buys product {old} {hit.sum()} times"
            raise ValueError(msg)
        rows[hit] = new
        if amount is not None:
            data[hit] = amount
    bio = system.bio_cols == col
    n_bio = int(bio.sum())
    return (rows, np.full(rows.size, node), data, system.tech_flip[keep]), (
        system.bio_rows[bio],
        np.full(n_bio, node),
        system.bio_data[bio],
    )


def foreground(
    system: System, at: dict[str, int], *, cop: float, renewable_share: float, heat_demand_kwh: float
) -> Foreground:
    """The heating foreground over ``system``; ``at`` maps ``NAMES`` to matrix indices (``locate``)."""
    base = system.profile.products + system.profile.flows
    node = lambda i: base + i  # noqa: E731
    heat = heat_demand_kwh * YEARS * MJ_PER_KWH  # MJ over the 20 years
    hp, hp_bio = _copy(system, at[HEAT_PUMP], node(HP), {at[GRID_CH]: (node(GRID), 1 / (MJ_PER_KWH * cop))})
    burner, burner_bio = _copy(
        system, at[BURNER], node(BURNER_NODE), {at[GRID_ENTSOE]: (node(GRID), None), at[GAS_CH]: (at[GAS_NL], None)}
    )
    boiler, boiler_bio = _copy(system, at[BOILER], node(BOILER_NODE), {at[BURNER]: (node(BURNER_NODE), None)})
    diag = np.arange(base, base + len(NODES))
    tech = [
        (diag, diag, np.ones(diag.size), np.zeros(diag.size, dtype=bool)),
        _inputs(node(GRID), [(at[GRID_NL], 1 - renewable_share), (at[PV_NL], renewable_share)]),
        hp,
        burner,
        boiler,
        _inputs(node(HP_YEARS), [(node(HP), heat)]),
        _inputs(node(BOILER_YEARS), [(node(BOILER_NODE), heat)]),
    ]
    bio = [hp_bio, burner_bio, boiler_bio]
    rows, cols, data, flip = (np.concatenate(parts) for parts in zip(*tech, strict=True))
    bio_rows, bio_cols, bio_data = (np.concatenate(parts) for parts in zip(*bio, strict=True))
    return Foreground(
        base,
        rows.astype(np.int64),
        cols.astype(np.int64),
        data.astype(np.float64),
        flip.astype(np.bool_),
        bio_rows.astype(np.int64),
        bio_cols.astype(np.int64),
        bio_data.astype(np.float64),
    )


def without_grid(fg: Foreground) -> Foreground:
    """``fg`` with no input into or out of ``grid NL``: the part no scenario changes.

    A scenario's electricity then comes in through the demand instead (``scenario_demand``).
    """
    grid = fg.id(GRID)
    keep = ~(fg.tech_flip & ((fg.tech_rows == grid) | (fg.tech_cols == grid)))
    return fg._replace(
        tech_rows=fg.tech_rows[keep],
        tech_cols=fg.tech_cols[keep],
        tech_data=fg.tech_data[keep],
        tech_flip=fg.tech_flip[keep],
    )


def electricity(fg: Foreground, node: int) -> float:
    """The kWh of ``grid NL`` that one unit of ``node`` draws, through the foreground."""
    k = len(NODES)
    inside = fg.tech_rows >= fg.base
    a = np.zeros((k, k))
    signed = np.where(fg.tech_flip, -fg.tech_data, fg.tech_data)
    np.add.at(a, (fg.tech_rows[inside] - fg.base, fg.tech_cols[inside] - fg.base), signed[inside])
    return float(np.linalg.solve(a, np.eye(k)[node])[GRID])


def scenario_demand(fg: Foreground, node: int) -> dict[int, float]:
    """The demand on ``without_grid(fg)`` that scores as one unit of ``node`` on ``fg``.

    Every scenario's foreground differs only in how much ``grid NL`` the options draw and what it
    is made of, so one factorization of the fixed part serves them all: the option itself, plus
    that electricity's share of each of the grid's suppliers.
    """
    kwh = electricity(fg, node)
    grid = fg.tech_flip & (fg.tech_cols == fg.id(GRID))
    demand = {fg.id(node): 1.0}
    for row, amount in zip(fg.tech_rows[grid], fg.tech_data[grid], strict=True):
        demand[int(row)] = demand.get(int(row), 0.0) + kwh * float(amount)
    return demand


def scenarios(n: int) -> list[tuple[float, float]]:
    """``n`` (cop, renewable_share) pairs on a square grid: cop 2.5 to 4.5, share 0 to 1."""
    k = round(n**0.5)
    if k * k != n:
        msg = f"{n} scenarios: the grid needs a square number"
        raise ValueError(msg)
    return [(float(c), float(s)) for c in np.linspace(2.5, 4.5, k) for s in np.linspace(0.0, 1.0, k)]


def reference(system: System, fg: Foreground, demands: list[dict[int, float]]) -> list[list[float]]:
    """Score of each demand per method, ``scores[d][m]``, by ``neumann`` on BAFU and ``fg`` together.

    No Brightway code and no factorization. A foreground node's unit is scaled by twice its
    largest input, so the 20 years' 720,000 MJ do not swamp the series' stopping rule and its
    columns sum below 1. It shares ``foreground`` with the cases, so it checks bw2calc's solve,
    not the foreground model; ``tests/test_heating.py`` checks the model.
    """
    n, k = system.profile.products, len(NODES)
    pos = lambda ids: np.where(ids >= fg.base, ids - fg.base + n, ids)  # noqa: E731
    rows = np.concatenate([system.tech_rows, pos(fg.tech_rows)])
    cols = np.concatenate([system.tech_cols, pos(fg.tech_cols)])
    data = np.concatenate([system.tech_data, fg.tech_data])
    flip = np.concatenate([system.tech_flip, fg.tech_flip])
    a = sparse.csr_matrix((np.where(flip, -data, data), (rows, cols)), shape=(n + k, n + k))
    inputs = sparse.identity(n + k, format="csr") - a
    scale = np.ones(n + k)
    scale[n:] = 0.5 / np.maximum(1.0, np.asarray(abs(inputs).max(axis=0).todense()).ravel()[n:])
    d = np.zeros((n + k, len(demands)))
    for j, demand in enumerate(demands):
        for i, amount in demand.items():
            d[pos(np.array(i)), j] += amount
    supply = neumann(inputs, d, scale=scale)
    bio = sparse.csr_matrix(
        (
            np.concatenate([system.bio_data, fg.bio_data]),
            (np.concatenate([system.bio_rows, fg.bio_rows]) - n, pos(np.concatenate([system.bio_cols, fg.bio_cols]))),
        ),
        shape=(system.profile.flows, n + k),
    )
    inventory = bio @ supply
    return [
        [float(inventory[f - n, j] @ c) for f, c in zip(system.cf_flows, system.cf_data, strict=True)]
        for j in range(len(demands))
    ]


def datapackage(fg: Foreground) -> object:
    """``fg`` as an in-memory bw_processing datapackage, to load beside BAFU's."""
    import bw_processing as bwp  # noqa: PLC0415 - only the container has it

    def indices(rows: NDArray, cols: NDArray) -> np.ndarray:
        arr = np.empty(rows.size, dtype=bwp.INDICES_DTYPE)
        arr["row"], arr["col"] = rows, cols
        return arr

    dp = bwp.create_datapackage()
    dp.add_persistent_vector(
        matrix="technosphere_matrix",
        name="heating-technosphere",
        indices_array=indices(fg.tech_rows, fg.tech_cols),
        data_array=fg.tech_data,
        flip_array=fg.tech_flip,
    )
    dp.add_persistent_vector(
        matrix="biosphere_matrix",
        name="heating-biosphere",
        indices_array=indices(fg.bio_rows, fg.bio_cols),
        data_array=fg.bio_data,
    )
    return dp


def bw2data(system: System, fg: Foreground) -> dict:
    """Foreground records linked to ``system.bw2data(db="background", bio="bio")``.

    Codes use foreground node indices; background products and flows keep ``p<i>`` and ``f<j>``.
    Values stay in memory and must not be published.
    """
    records: dict = {
        ("foreground", str(i)): {
            "name": name,
            "reference product": name,
            "unit": "unit",
            "location": "NL",
            "exchanges": [],
        }
        for i, name in enumerate(NODES)
    }
    for r, c, amount, flip in zip(fg.tech_rows, fg.tech_cols, fg.tech_data, fg.tech_flip, strict=True):
        key = ("foreground", str(r - fg.base)) if r >= fg.base else ("background", f"p{r}")
        records["foreground", str(c - fg.base)]["exchanges"].append(
            {"input": key, "amount": float(amount), "type": "technosphere" if flip else "production"}
        )
    for r, c, amount in zip(fg.bio_rows, fg.bio_cols, fg.bio_data, strict=True):
        records["foreground", str(c - fg.base)]["exchanges"].append(
            {"input": ("bio", f"f{r - system.flow_offset}"), "amount": float(amount), "type": "biosphere"}
        )
    return records


def stage_scores(system: System, fg: Foreground, at: dict[str, int]) -> dict[str, list[list[float]]]:
    """Each foreground stage's score per option and method, including its complete upstream chain.

    The four disjoint stages sum to the total. These aggregate scores can be published;
    the underlying inventory entries cannot.
    """
    outside = fg.tech_flip & (fg.tech_rows < fg.base)
    electricity_inputs = outside & (fg.tech_cols == fg.id(GRID))
    gas_inputs = outside & (fg.tech_rows == at[GAS_NL])
    other_inputs = outside & ~electricity_inputs & ~gas_inputs
    stages = {
        "Electricity supply": electricity_inputs,
        "Gas supply": gas_inputs,
        "Other supply chains": other_inputs,
        "Foreground emissions": np.zeros(fg.tech_data.size, dtype=bool),
    }
    demands = [{fg.id(node): 1.0} for node in OPTIONS.values()]
    return {
        name: reference(
            system,
            fg._replace(
                tech_data=np.where(outside & ~keep, 0.0, fg.tech_data),
                bio_data=fg.bio_data if name == "Foreground emissions" else np.zeros_like(fg.bio_data),
            ),
            demands,
        )
        for name, keep in stages.items()
    }


FlowMetadata = tuple[str, str, tuple[str, ...]]


def expand_factors(flows: Mapping[int, FlowMetadata], factors: dict[int, float]) -> dict[int, float]:
    """Add missing descendants of uniquely characterized parents; exact flow factors always win.

    Names and units must match exactly. Categories must be a strict prefix; the deepest
    parent wins. Ambiguous parents raise instead of silently choosing one.
    """
    expanded = factors.copy()
    for target, (name, unit, categories) in flows.items():
        if target in factors:
            continue
        for depth in range(len(categories) - 1, 0, -1):
            parents = [source for source in factors if flows[source] == (name, unit, categories[:depth])]
            if len(parents) > 1:
                msg = f"ambiguous parent factors for flow {target} at {categories[:depth]}"
                raise ValueError(msg)
            if parents:
                expanded[target] = factors[parents[0]]
                break
    return expanded


def corrected_system(system: System) -> System:
    """The heating case's BAFU system with parent-compartment factors expanded to emitted descendants.

    The archive and the general BAFU benchmarks stay unchanged. This matches Brightway's
    ``match_subcategories`` convention, extended to choose the most specific unique parent.
    No external factor values or cross-substance aliases are introduced. The factors are cached
    beside the archive (``_derived``), so only the first process of a run reads it again.
    """
    from bwbench import bafu, useeio  # noqa: PLC0415 - archive reading needs container dependencies

    archive = bafu.archive()
    cached = _derived(archive, "factors.npz", system.flow_offset)
    if cached.exists():
        with np.load(cached) as z:
            n = len(z.files) // 2
            mapped, values = [z[f"flows{i}"] for i in range(n)], [z[f"data{i}"] for i in range(n)]
        return replace(system, name=f"{system.name}-heating{VERSION}", cf_flows=mapped, cf_data=values)
    _, bio, methods = useeio.read(archive, bafu.METHODS)
    flow_ids = np.unique(bio[0]["row"])
    needed = set(flow_ids) | {int(i) for ids, _ in methods for i in ids}
    with tempfile.TemporaryDirectory() as tmp, tarfile.open(archive) as tar:
        member = next(m for m in tar.getmembers() if m.name.endswith("/lci/databases.db"))
        tar.extract(member, tmp, filter="data")
        with sqlite3.connect(Path(tmp) / member.name) as con:
            metadata = {}
            for i, blob in con.execute("select id, data from activitydataset"):
                if i in needed:
                    # The archive's checksum is pinned and verified before any metadata is read.
                    data = pickle.loads(blob)  # noqa: S301
                    metadata[i] = (data["name"], data["unit"], tuple(data["categories"]))
    mapped, values = [], []
    for ids, factors in methods:
        # Repeated vector entries contribute to one flow's factor, as in the original matrix.
        source = {int(i): float(factors[ids == i].sum()) for i in np.unique(ids)}
        expanded = expand_factors(metadata, source)
        keep = np.isin(ids, flow_ids)
        extra = [int(i) for i in flow_ids if i not in source and i in expanded]
        combined = np.concatenate([ids[keep], np.array(extra, dtype=np.int64)])
        mapped.append(np.searchsorted(flow_ids, combined).astype(np.int64) + system.flow_offset)
        values.append(np.concatenate([factors[keep], [expanded[i] for i in extra]]).astype(np.float64))
    out = io.BytesIO()
    np.savez(out, **{f"flows{i}": a for i, a in enumerate(mapped)}, **{f"data{i}": a for i, a in enumerate(values)})
    _keep(cached, out.getvalue())
    return replace(system, name=f"{system.name}-heating{VERSION}", cf_flows=mapped, cf_data=values)
