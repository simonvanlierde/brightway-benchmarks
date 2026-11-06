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
(``bwbench.bafu``). Building and checking the arrays needs only numpy and scipy; the
datapackage needs bw_processing, so it runs in the benchmark container.
"""

from __future__ import annotations

import sqlite3
import tarfile
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple

import numpy as np
from scipy import sparse

from bwbench.synth import neumann

if TYPE_CHECKING:
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
VERSION = "1"  # bump with any change to the foreground or the heating cases: it restarts their history
MJ_PER_KWH = 3.6
# - cop 3.0: field trials put air-source heat pumps' seasonal performance factor near 3
#   (Staffell et al. 2012, Energy Environ. Sci. 5, 9291).
# - 10,000 kWh of heat a year: a Dutch household burns about 1,000 to 1,200 m³ of gas a year
#   (CBS), at 9.8 kWh/m³ and a boiler efficiency near 90%.
# - renewable_share 0: BAFU's Dutch grid as it is; 1 runs on Dutch photovoltaics alone.
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
    ``ValueError`` for a name that is missing or not unique.
    """
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
    return at


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
