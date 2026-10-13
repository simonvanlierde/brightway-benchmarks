import os
import types
from pathlib import Path

import numpy as np
import pytest
from scipy import sparse

from bwbench import synth
from bwbench.synth import MAX_COLUMN_SUM, PROFILES, as_bw2data, neumann, system

SMALL = ["smoke", "stress-random"]


def small(name: str, **kw: object) -> synth.System:
    return system(name, **({"products": 300} if name == "stress-random" else {}), **kw)


@pytest.mark.parametrize("name", SMALL)
def test_same_seed_same_system(name: str):
    a = small(name, seed=3)
    synth._build.cache_clear()  # noqa: SLF001 - otherwise b is the same cached object
    b = small(name, seed=3)
    assert a is not b
    for field in ("tech_rows", "tech_cols", "tech_data", "bio_data", "scale"):
        assert getattr(a, field).tobytes() == getattr(b, field).tobytes()
    assert a.reference == b.reference
    assert not np.array_equal(a.tech_data, small(name, seed=4).tech_data)


@pytest.mark.parametrize("name", SMALL)
def test_unit_diagonal_and_no_repeated_cells(name: str):
    s = small(name)
    assert np.allclose(s.technosphere().diagonal(), 1.0)
    cells = s.tech_rows * s.profile.products + s.tech_cols
    assert np.unique(cells).size == cells.size


@pytest.mark.parametrize("name", SMALL)
def test_columns_sum_below_one_without_units(name: str):
    s = small(name)
    x = sparse.identity(s.profile.products) - s.technosphere()
    x0 = sparse.diags(1 / s.scale) @ x @ sparse.diags(s.scale)
    assert x0.min() >= 0  # units and signs are all in the scale
    assert abs(x0).sum(axis=0).max() <= MAX_COLUMN_SUM + 1e-12


def test_tiered_has_units_signs_and_loops():
    s = system("smoke")
    assert (s.scale < 0).any()
    assert np.ptp(np.log10(np.abs(s.scale))) > 1
    assert (s.tech_data[s.tech_flip] < 0).any()


@pytest.mark.parametrize("name", SMALL)
def test_reference_scores_match_a_dense_solve(name: str):
    s = small(name)
    n = s.profile.products
    supply = np.linalg.solve(s.technosphere().toarray(), np.eye(n, 30))
    g = s.biosphere().toarray() @ supply
    dense = [[g[f - s.flow_offset, p] @ c for f, c in zip(s.cf_flows, s.cf_data, strict=True)] for p in range(30)]
    assert np.allclose(s.reference, dense, rtol=1e-12)
    assert np.min(dense) > 0


def test_profiles_take_overrides():
    s = system("smoke", products=150)
    assert s.profile.products == 150
    assert s.technosphere().shape == (150, 150)
    with pytest.raises(TypeError):
        system("smoke", no_such_field=1)


def test_bw2data_form_has_every_exchange():
    s = system("smoke")
    bio, tech, cfs = as_bw2data(s)
    assert len(bio) == s.profile.flows
    assert len(tech) == s.profile.products
    assert sum(len(v["exchanges"]) for v in tech.values()) == s.tech_data.size + s.bio_data.size
    assert [len(c) for c in cfs] == [f.size for f in s.cf_flows]


def test_neumann_solves_with_units_and_refuses_to_diverge():
    s = system("smoke")
    a = s.technosphere()
    demand = np.zeros(s.profile.products)
    demand[5] = 2.0
    x = neumann(sparse.identity(s.profile.products, format="csr") - a, demand, scale=s.scale)
    # Entries the demand cannot reach are 0 here and rounding noise (about 1e-19) in a dense solve.
    assert np.allclose(x, np.linalg.solve(a.toarray(), demand), rtol=1e-12, atol=1e-15 * np.abs(x).max())
    with pytest.raises(ArithmeticError):
        neumann(sparse.csr_matrix([[0.0, 1.0], [1.0, 0.0]]), np.ones(2))


def test_neumann_stops_on_the_tail_bound_at_a_high_radius():
    # A chain whose columns sum to 0.95: the old stopping rule held only up to 0.5.
    n = 50
    x = sparse.diags([np.full(n - 1, 0.95)], [1], format="csr")
    demand = np.zeros(n)
    demand[-1] = 1.0
    got = neumann(x, demand)
    assert np.allclose(got, np.linalg.solve(np.eye(n) - x.toarray(), demand), rtol=1e-14, atol=0)


def test_neumann_converges_past_a_column_sum_of_one():
    # Column 1 sums to 2, but the spectral radius is sqrt(0.2): a Monte Carlo draw can look like this.
    x = sparse.csr_matrix([[0.0, 2.0], [0.1, 0.0]])
    got = neumann(x, np.array([1.0, 1.0]))
    assert np.allclose(got, np.linalg.solve(np.eye(2) - x.toarray(), [1.0, 1.0]), rtol=1e-14, atol=0)


def test_cache_folder_follows_everything_that_shapes_the_files(monkeypatch: pytest.MonkeyPatch):
    def key(seed: int = 0, *, uncertain: bool = False, bwp_version: str = "1.6", **kw: object) -> Path:
        p = synth.profile("ecoinvent", **kw)
        return synth.cache_folder("ecoinvent", p, seed=seed, uncertain=uncertain, bwp_version=bwp_version)

    base = key()
    assert base == key()
    assert len({base, key(seed=1), key(uncertain=True), key(bwp_version="1.5"), key(products=8_000)}) == 5
    monkeypatch.setattr(synth, "GENERATOR_VERSION", "test")
    assert key() != base


def test_cache_follows_the_calibration_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    p = synth.profile("ecoinvent")
    assert p.target
    target = tmp_path / p.target
    target.write_bytes((synth.PROFILES_DIR / p.target).read_bytes())
    monkeypatch.setattr(synth, "PROFILES_DIR", tmp_path)
    before = p.digest()
    target.write_text(target.read_text() + " ")
    assert p.digest() != before


def test_datapackages_regenerate_when_the_profile_changes(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    written = []

    def fake_write(s: synth.System, folder: Path, **_: object) -> Path:
        folder.mkdir(parents=True)
        (folder / "reference.json").write_text("{}")
        written.append(s.profile.products)
        return folder

    monkeypatch.setattr(synth, "write_datapackages", fake_write)
    monkeypatch.setattr(synth, "version", lambda _: "1.6")
    monkeypatch.setattr(synth, "data_root", lambda: tmp_path)
    first = system("smoke").datapackages()
    assert system("smoke").datapackages() == first
    assert len(written) == 1
    assert system("smoke", products=201).datapackages() != first
    assert written == [200, 201]
    assert not list(tmp_path.glob("*.tmp-*"))


def test_profile_version_follows_every_profile_not_the_selection(monkeypatch: pytest.MonkeyPatch):
    base = synth.profile_version()
    assert synth.profile_version() == base
    monkeypatch.setitem(PROFILES, "ecoinvent", synth.profile("ecoinvent", back=0.2))
    assert synth.profile_version() != base


def test_an_edited_profile_never_returns_a_stale_system(monkeypatch: pytest.MonkeyPatch):
    assert system("smoke").profile.products == 200
    monkeypatch.setitem(PROFILES, "smoke", synth.profile("smoke", products=150))
    assert system("smoke").profile.products == 150


def test_shared_arrays_are_read_only():
    s = system("smoke")
    with pytest.raises(ValueError, match="read-only"):
        s.tech_data[0] = 2.0


def test_neumann_score_matches_the_reference():
    s = system("smoke")
    n = s.profile.products
    demand = np.zeros(n)
    demand[0] = 1.0
    cf = np.zeros(s.profile.flows)
    cf[s.cf_flows[0] - s.flow_offset] = s.cf_data[0]
    lca = types.SimpleNamespace(
        technosphere_matrix=s.technosphere(),
        demand_array=demand,
        biosphere_matrix=s.biosphere(),
        characterization_matrix=sparse.diags(cf),
    )
    assert synth.neumann_score(lca, s.scale) == pytest.approx(s.reference[0][0], rel=1e-12)


def test_skip_unless_factorizable():
    synth.skip_unless_factorizable("smoke", pardiso=False, factorizations=1_000)
    synth.skip_unless_factorizable("regional", pardiso=True, factorizations=10)
    with pytest.raises(NotImplementedError, match="without PyPardiso"):
        synth.skip_unless_factorizable("mc100k", pardiso=False)
    synth.skip_unless_factorizable("ecoinvent", pardiso=False, factorizations=2)  # about 6 min
    with pytest.raises(NotImplementedError):
        synth.skip_unless_factorizable("ecoinvent", pardiso=False, factorizations=12)  # Monte Carlo with LCA


def test_stale_tmp_folders_are_swept(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setattr(synth, "write_datapackages", lambda _, folder: folder.mkdir(parents=True))
    monkeypatch.setattr(synth, "version", lambda _: "1.6")
    monkeypatch.setattr(synth, "data_root", lambda: tmp_path)
    s = system("smoke")
    folder = synth.cache_folder(s.name, s.profile, seed=0, uncertain=False)
    old, fresh = folder.with_name(f"{folder.name}.tmp-old"), folder.with_name(f"{folder.name}.tmp-new")
    old.mkdir(parents=True)
    fresh.mkdir()
    os.utime(old, (0, 0))
    s.datapackages()
    assert not old.exists()
    assert fresh.exists()  # may still be another run's
