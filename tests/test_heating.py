import pickle
import sqlite3
import tarfile
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest
from hypothesis import given
from hypothesis import strategies as st

from bwbench import bafu, heating, synth, useeio

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
# (supplier, consumer, amount) inputs, invented: the heat pump's own 0.05 kWh of CH grid is what the copy replaces.
INPUTS = [
    (AT[heating.GRID_CH], AT[heating.HEAT_PUMP], 0.05),
    (AT[heating.GAS_CH], AT[heating.HEAT_PUMP], 1e-3),
    (AT[heating.GRID_ENTSOE], AT[heating.BURNER], 2e-3),
    (AT[heating.GAS_CH], AT[heating.BURNER], 1.0),
    (AT[heating.BURNER], AT[heating.BOILER], 0.9),
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
    assert into(heating.BURNER_NODE) == {fg.id(heating.GRID): 2e-3, AT[heating.GAS_NL]: 1.0}
    assert into(heating.BOILER_NODE) == {fg.id(heating.BURNER_NODE): 0.9}
    assert into(heating.HP_YEARS) == {fg.id(heating.HP): pytest.approx(20 * 3.6)}
    assert into(heating.BOILER_YEARS) == {fg.id(heating.BOILER_NODE): pytest.approx(20 * 3.6)}
    # Each node produces only itself: the copied process's own production is left out.
    production = [(int(r), int(c)) for r, c, f in zip(fg.tech_rows, fg.tech_cols, fg.tech_flip, strict=True) if not f]
    assert all(r == c for r, c in production)
    # The copy emits what its source emits.
    emits = lambda ids, col: sorted(  # noqa: E731
        (int(r), float(d)) for r, c, d in zip(ids.bio_rows, ids.bio_cols, ids.bio_data, strict=True) if c == col
    )
    assert emits(fg, fg.id(heating.HP)) == emits(system, AT[heating.HEAT_PUMP])
    assert emits(fg, fg.id(heating.BURNER_NODE)) == emits(system, AT[heating.BURNER])


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


def test_locate_maps_product_names_to_matrix_indices(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
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
    archive.with_name("elsewhere").write_bytes(archive.read_bytes())
    archive.write_bytes(b"")  # another archive: the map cached for the old one must not answer
    with pytest.raises(tarfile.ReadError):
        heating.locate(archive, ("a {CH}",), ids)
    archive.write_bytes(archive.with_name("elsewhere").read_bytes())
    monkeypatch.setattr(tarfile, "open", lambda *_, **__: pytest.fail("read the archive again"))
    assert heating.locate(archive, ("a {CH}",), ids) == {"a {CH}": 2}


def test_bw2data_preserves_foreground_entries():
    system = toy()
    fg = heating.foreground(system, AT, **heating.DEFAULTS)
    records = heating.bw2data(system, fg)
    assert len(records) == len(heating.NODES)
    assert sum(len(r["exchanges"]) for r in records.values()) == fg.tech_data.size + fg.bio_data.size
    for i in range(len(heating.NODES)):
        exchanges = records["foreground", str(i)]["exchanges"]
        assert {"input": ("foreground", str(i)), "amount": 1.0, "type": "production"} in exchanges
    assert any(e["input"][0] == "background" for r in records.values() for e in r["exchanges"])
    assert any(e["input"][0] == "bio" for r in records.values() for e in r["exchanges"])


def test_stage_scores_partition_the_total():
    system = toy()
    fg = heating.foreground(system, AT, **heating.DEFAULTS)
    stages = heating.stage_scores(system, fg, AT)
    total = heating.reference(system, fg, [{fg.id(node): 1.0} for node in heating.OPTIONS.values()])
    np.testing.assert_allclose(np.sum(list(stages.values()), axis=0), total, rtol=1e-11, atol=1e-10, strict=True)


def test_electricity_stage_contains_its_upstream_chain():
    system = toy()
    fg = heating.foreground(system, AT, **heating.DEFAULTS)
    stages = heating.stage_scores(system, fg, AT)
    grid_scores = np.array(heating.reference(system, fg, [{fg.id(heating.GRID): 1.0}])[0])
    for i, node in enumerate(heating.OPTIONS.values()):
        expected = grid_scores * heating.electricity(fg, node)
        # The stage decomposition and unit-grid demand differ only by linear scaling.
        np.testing.assert_allclose(stages["Electricity supply"][i], expected, rtol=1e-11, atol=1e-10, strict=True)


def test_missing_subcompartment_inherits_parent_factor():
    flows = {0: ("carbon", "kg", ("air",)), 1: ("carbon", "kg", ("air", "urban"))}
    assert heating.expand_factors(flows, {0: 2.0}) == {0: 2.0, 1: 2.0}


def test_exact_factor_including_zero_wins_over_parent():
    flows = {0: ("carbon", "kg", ("air",)), 1: ("carbon", "kg", ("air", "urban"))}
    assert heating.expand_factors(flows, {0: 2.0, 1: 0.0}) == {0: 2.0, 1: 0.0}


def test_factor_does_not_cross_substance_unit_or_compartment():
    flows = {
        0: ("carbon", "kg", ("air",)),
        1: ("nitrogen", "kg", ("air", "urban")),
        2: ("carbon", "g", ("air", "urban")),
        3: ("carbon", "kg", ("water", "river")),
    }
    assert heating.expand_factors(flows, {0: 2.0}) == {0: 2.0}


def test_most_specific_parent_factor_wins():
    flows = {
        0: ("carbon", "kg", ("air",)),
        1: ("carbon", "kg", ("air", "urban")),
        2: ("carbon", "kg", ("air", "urban", "low")),
    }
    assert heating.expand_factors(flows, {0: 2.0, 1: 3.0}) == {0: 2.0, 1: 3.0, 2: 3.0}


def test_ambiguous_parent_factors_raise():
    flows = {
        0: ("carbon", "kg", ("air",)),
        1: ("carbon", "kg", ("air",)),
        2: ("carbon", "kg", ("air", "urban")),
    }
    with pytest.raises(ValueError, match="ambiguous parent"):
        heating.expand_factors(flows, {0: 2.0, 1: 3.0})


def test_inherited_factor_restores_the_hand_calculated_combustion_stage():
    original = toy()
    flows = {N: ("carbon", "kg", ("air",)), N + 1: ("carbon", "kg", ("air", "urban"))}
    expanded = heating.expand_factors(flows, {N: 2.0})
    corrected = replace(
        original,
        cf_flows=[np.array(list(expanded))],
        cf_data=[np.array(list(expanded.values()))],
    )
    fg = heating.foreground(corrected, AT, **heating.DEFAULTS)
    direct = heating.stage_scores(corrected, fg, AT)["Foreground emissions"][1][0]
    # The toy boiler emits 0.9 per MJ and buys 0.9 MJ of burner, which emits 0.8 + 0.056.
    expected = 10_000 * 20 * 3.6 * 2 * (0.9 + 0.9 * (0.8 + 0.056))
    assert direct == pytest.approx(expected, rel=1e-11, abs=1e-8)
    np.testing.assert_array_equal(original.cf_data[0], [1.0, 2.0])


@given(st.dictionaries(st.integers(0, 3), st.floats(allow_nan=False, allow_infinity=False)))
def test_factor_expansion_is_idempotent_and_preserves_explicit_factors(factors: dict[int, float]):
    flows = {
        0: ("carbon", "kg", ("air",)),
        1: ("carbon", "kg", ("air", "urban")),
        2: ("carbon", "kg", ("air", "urban", "low")),
        3: ("nitrogen", "kg", ("air", "urban")),
    }
    original = factors.copy()
    expanded = heating.expand_factors(flows, factors)
    assert expanded == heating.expand_factors(flows, expanded)
    assert all(expanded[i] == factor for i, factor in original.items())
    assert factors == original


@pytest.mark.parametrize("parent_emitted", [True, False])
@pytest.mark.parametrize("repeated_entries", [True, False])
def test_corrected_system_preserves_raw_data_and_uses_a_separate_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, parent_emitted: bool, repeated_entries: bool
):
    database = tmp_path / "databases.db"
    with sqlite3.connect(database) as con:
        con.execute("create table activitydataset (id integer, data blob)")
        for i, categories in [(100, ("air",)), (200, ("air", "urban"))]:
            blob = pickle.dumps({"name": "carbon", "unit": "kg", "categories": categories})
            con.execute("insert into activitydataset values (?, ?)", (i, blob))
    archive = tmp_path / "fixture.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(database, arcname="project/lci/databases.db")
    emitted = [(100, 1), (200, 1)] if parent_emitted else [(200, 1)]
    biosphere = np.array(emitted, dtype=[("row", "i8"), ("col", "i8")])
    monkeypatch.setattr(bafu, "archive", lambda: archive)
    amounts = [2.0, 3.0] if repeated_entries else [2.0]
    methods = [(np.full(len(amounts), 100), np.array(amounts))] * 2
    monkeypatch.setattr(useeio, "read", lambda *_: (None, (biosphere, None), methods))
    original = toy()
    original = replace(
        original,
        profile=replace(original.profile, flows=len(emitted)),
        bio_rows=original.bio_rows if parent_emitted else np.full_like(original.bio_rows, N),
        cf_flows=[np.full(len(amounts) if parent_emitted else 0, N, dtype=np.int64)] * 2,
        cf_data=[np.array(amounts if parent_emitted else [], dtype=np.float64)] * 2,
    )
    corrected = heating.corrected_system(original)
    expected_flows = [N] * len(amounts) + [N + 1] if parent_emitted else [N]
    expected_factors = [*amounts, sum(amounts)] if parent_emitted else [sum(amounts)]
    np.testing.assert_array_equal(corrected.cf_flows[0], expected_flows)
    np.testing.assert_array_equal(corrected.cf_data[0], expected_factors)
    np.testing.assert_array_equal(original.cf_data[0], amounts if parent_emitted else [])
    assert corrected.tech_data is original.tech_data
    assert corrected.bio_data is original.bio_data
    assert corrected.name != original.name
    # A second process reads the factors cached beside the archive, not the archive.
    monkeypatch.setattr(useeio, "read", lambda *_: pytest.fail("read the archive again"))
    again = heating.corrected_system(original)
    for a, b in zip(again.cf_flows + again.cf_data, corrected.cf_flows + corrected.cf_data, strict=True):
        np.testing.assert_array_equal(a, b)
    assert again.name == corrected.name
