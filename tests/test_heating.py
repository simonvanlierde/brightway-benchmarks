import sqlite3
import tarfile
from pathlib import Path

import numpy as np
import pytest

from bwbench import heating, synth

# A toy background with every product the foreground names, by index.
PRODUCTS = (
    heating.GRID_CH,
    heating.GRID_ENTSOE,
    heating.GAS_CH,
    heating.GRID_NL,
    heating.PV_NL,
    heating.GAS_NL,
    heating.HEAT_PUMP,
    heating.BURNER,
    heating.BOILER,
)
AT = {name: i for i, name in enumerate(PRODUCTS)}
N, FLOWS = len(PRODUCTS), 2
# (supplier, consumer, amount) inputs, as BAFU holds them: the heat pump's own 0.0631 kWh of CH grid.
INPUTS = [
    (AT[heating.GRID_CH], AT[heating.HEAT_PUMP], 0.0631),
    (AT[heating.GAS_CH], AT[heating.HEAT_PUMP], 1e-3),
    (AT[heating.GRID_ENTSOE], AT[heating.BURNER], 7e-4),
    (AT[heating.GAS_CH], AT[heating.BURNER], 1.0),
    (AT[heating.BURNER], AT[heating.BOILER], 0.913),
    (AT[heating.GRID_ENTSOE], AT[heating.GRID_CH], 0.1),
    (AT[heating.PV_NL], AT[heating.GRID_NL], 0.05),
    (AT[heating.GRID_NL], AT[heating.GAS_NL], 0.02),
    (AT[heating.GAS_NL], AT[heating.GRID_NL], 0.3),  # a loop, as real grids have
]


def toy() -> synth.System:
    diag = np.arange(N)
    rows, cols, amounts = (np.array(v) for v in zip(*INPUTS, strict=True))
    bio_cols = np.concatenate([diag, [AT[heating.BURNER]]])
    bio_rows = np.concatenate([np.full(N, N), [N + 1]])  # every product emits flow 0; the burner also flow 1
    return synth.System(
        "toy",
        synth.Profile(products=N, flows=FLOWS, builder="toy", methods=2),
        0,
        np.concatenate([diag, rows]),
        np.concatenate([diag, cols]),
        np.concatenate([np.ones(N), amounts]),
        np.concatenate([np.zeros(N, dtype=bool), np.ones(len(INPUTS), dtype=bool)]),
        bio_rows,
        bio_cols,
        np.concatenate([np.linspace(0.1, 0.9, N), [0.056]]),
        [np.array([N, N + 1]), np.array([N + 1])],
        [np.array([1.0, 2.0]), np.array([1.0])],
        np.ones(N),
    )


def dense_scores(system: synth.System, fg: heating.Foreground, demand: dict[int, float]) -> list[float]:
    """The scores of ``demand`` by a dense solve of background and foreground together."""
    k = len(heating.NODES)
    at = lambda ids: np.where(ids >= fg.base, ids - fg.base + N, ids)  # noqa: E731
    a = np.zeros((N + k, N + k))
    rows = np.concatenate([system.tech_rows, at(fg.tech_rows)])
    cols = np.concatenate([system.tech_cols, at(fg.tech_cols)])
    data = np.concatenate([system.tech_data, fg.tech_data])
    flip = np.concatenate([system.tech_flip, fg.tech_flip])
    np.add.at(a, (rows, cols), np.where(flip, -data, data))
    b = np.zeros((FLOWS, N + k))
    bio_rows = np.concatenate([system.bio_rows, fg.bio_rows]) - N
    np.add.at(
        b,
        (bio_rows, at(np.concatenate([system.bio_cols, fg.bio_cols]))),
        np.concatenate([system.bio_data, fg.bio_data]),
    )
    d = np.zeros(N + k)
    for i, amount in demand.items():
        d[at(np.array(i))] += amount
    inventory = b @ np.linalg.solve(a, d)
    return [float(inventory[f - N] @ c) for f, c in zip(system.cf_flows, system.cf_data, strict=True)]


def test_the_heat_pump_draws_one_over_cop_from_the_nl_mix_instead_of_its_own_electricity():
    system = toy()
    fg = heating.foreground(system, AT, cop=4.0, renewable_share=0.25, heat_demand_kwh=1.0)
    into = lambda node: {  # noqa: E731
        int(r): float(d)
        for r, c, d, f in zip(fg.tech_rows, fg.tech_cols, fg.tech_data, fg.tech_flip, strict=True)
        if c == fg.id(node) and f
    }
    assert into(heating.HP) == {fg.id(heating.GRID): pytest.approx(1 / (4.0 * 3.6)), AT[heating.GAS_CH]: 1e-3}
    assert into(heating.GRID) == {AT[heating.GRID_NL]: 0.75, AT[heating.PV_NL]: 0.25}
    assert into(heating.BURNER_NODE) == {fg.id(heating.GRID): 7e-4, AT[heating.GAS_NL]: 1.0}
    assert into(heating.BOILER_NODE) == {fg.id(heating.BURNER_NODE): 0.913}
    assert into(heating.HP_YEARS) == {fg.id(heating.HP): pytest.approx(20 * 3.6)}


@pytest.mark.parametrize("option", heating.OPTIONS.values())
def test_reference_matches_a_dense_solve(option: int):
    system = toy()
    fg = heating.foreground(system, AT, **heating.DEFAULTS)
    got = heating.reference(system, fg, [{fg.id(option): 1.0}])
    assert got[0] == pytest.approx(dense_scores(system, fg, {fg.id(option): 1.0}), rel=1e-12)


@pytest.mark.parametrize(("cop", "share"), [(2.5, 0.0), (3.0, 0.4), (4.5, 1.0)])
def test_a_scenario_as_a_demand_on_the_fixed_foreground_scores_as_its_rebuilt_foreground(cop: float, share: float):
    system = toy()
    fixed = heating.without_grid(heating.foreground(system, AT, **heating.DEFAULTS))
    fg = heating.foreground(system, AT, cop=cop, renewable_share=share, heat_demand_kwh=10_000)
    for option in heating.OPTIONS.values():
        demand = heating.scenario_demand(fg, option)
        assert dense_scores(system, fixed, demand) == pytest.approx(
            dense_scores(system, fg, {fg.id(option): 1.0}), rel=1e-12
        )


def test_scenarios_span_the_grid():
    assert heating.scenarios(4) == [(2.5, 0.0), (2.5, 1.0), (4.5, 0.0), (4.5, 1.0)]
    with pytest.raises(ValueError, match="square"):
        heating.scenarios(5)


def test_locate_maps_product_names_to_matrix_indices(tmp_path: Path):
    db = tmp_path / "p" / "lci" / "databases.db"
    db.parent.mkdir(parents=True)
    with sqlite3.connect(db) as con:
        con.execute("create table activitydataset (id integer, product text)")
        con.executemany("insert into activitydataset values (?, ?)", [(90, "a {CH}"), (7, "b {NL}"), (8, "b {NL}")])
    archive = tmp_path / "a.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(tmp_path / "p", arcname="p")
    ids = np.array([7, 50, 90])  # the processes in matrix order
    assert heating.locate(archive, ("a {CH}",), ids) == {"a {CH}": 2}
    with pytest.raises(ValueError, match=r"b \{NL\}"):
        heating.locate(archive, ("b {NL}",), ids)
    with pytest.raises(ValueError, match=r"c \{CH\}"):
        heating.locate(archive, ("c {CH}",), ids)
