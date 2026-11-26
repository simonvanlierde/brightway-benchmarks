import hashlib
import os
import types
from pathlib import Path

import numpy as np
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from scipy import sparse

from bwbench import synth
from bwbench.matrices import System, neumann_score
from bwbench.profiles import PROFILES, profile
from bwbench.synth import MAX_COLUMN_SUM, system

SMALL = ["smoke", "stress-random"]


@given(n=st.integers(min_value=1, max_value=500), cap=st.integers(min_value=1, max_value=200))
def test_families_cover_every_product_without_exceeding_the_cap(n: int, cap: int):
    p = profile("smoke", family_max=cap)
    fam, first = synth._families(p, np.random.default_rng(0), n)  # noqa: SLF001
    assert len(fam) == n
    sizes = np.bincount(fam)
    assert np.all((sizes >= 1) & (sizes <= cap))
    np.testing.assert_array_equal(first, np.r_[0, np.cumsum(sizes)[:-1]])


def test_family_input_distribution_stays_fixed_when_members_are_shuffled():
    p = profile("ecoinvent")
    fam, first = synth._families(p, np.random.default_rng(0), p.products)  # noqa: SLF001
    a = synth._family_inputs(p, np.random.default_rng(0), fam)  # noqa: SLF001
    b = synth._family_inputs(p, np.random.default_rng(1), fam)  # noqa: SLF001
    np.testing.assert_array_equal(np.sort(a[first]), np.sort(b[first]))
    assert not np.array_equal(a, b)


def small(name: str, **kw: object) -> System:
    # ty checks the unpacked dict's int against every keyword, `uncertain: bool` included.
    return system(name, **({"products": 300} if name == "stress-random" else {}), **kw)  # ty: ignore[invalid-argument-type]


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


def test_cache_folder_follows_everything_that_shapes_the_files(monkeypatch: pytest.MonkeyPatch):
    def key(seed: int = 0, *, uncertain: bool = False, bwp_version: str = "1.6", **kw: object) -> Path:
        p = profile("ecoinvent", **kw)
        return synth.cache_folder("ecoinvent", p, seed=seed, uncertain=uncertain, bwp_version=bwp_version)

    base = key()
    assert base == key()
    assert len({base, key(seed=1), key(uncertain=True), key(bwp_version="1.5"), key(products=8_000)}) == 5
    monkeypatch.setattr(synth, "GENERATOR_VERSION", "test")
    assert key() != base


def test_datapackages_regenerate_when_the_profile_changes(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    written = []

    def fake_write(s: System, folder: Path, **_: object) -> Path:
        folder.mkdir(parents=True)
        (folder / "reference.json").write_text("{}")
        written.append(s.profile.products)
        return folder

    monkeypatch.setattr(synth, "write_datapackages", fake_write)
    monkeypatch.setattr(synth, "version", lambda _: "1.6")
    monkeypatch.setattr(synth, "data_root", lambda: tmp_path)
    first = synth.datapackages(system("smoke"))
    assert synth.datapackages(system("smoke")) == first
    assert len(written) == 1
    assert synth.datapackages(system("smoke", products=201)) != first
    assert written == [200, 201]
    assert not list(tmp_path.glob("*.tmp-*"))


def test_profile_version_follows_every_profile_not_the_selection(monkeypatch: pytest.MonkeyPatch):
    base = synth.profile_version()
    assert synth.profile_version() == base
    monkeypatch.setitem(PROFILES, "ecoinvent", profile("ecoinvent", back=0.2))
    assert synth.profile_version() != base


def test_an_edited_profile_never_returns_a_stale_system(monkeypatch: pytest.MonkeyPatch):
    assert system("smoke").profile.products == 200
    monkeypatch.setitem(PROFILES, "smoke", profile("smoke", products=150))
    assert system("smoke").profile.products == 150


def test_shared_arrays_are_read_only():
    s = system("smoke")
    with pytest.raises(ValueError, match="read-only"):
        s.tech_data[0] = 2.0
    for a in (s.region, s.sector):
        assert a is not None
        assert not a.flags.writeable


def test_skip_unless_factorizable():
    synth.skip_unless_factorizable("smoke", pardiso=False, timeout=600, factorizations=1_000)
    synth.skip_unless_factorizable("regional", pardiso=True, timeout=600, factorizations=10)
    with pytest.raises(NotImplementedError, match="without PyPardiso"):
        synth.skip_unless_factorizable("mc100k", pardiso=False, timeout=1800)
    synth.skip_unless_factorizable("ecoinvent", pardiso=False, timeout=600, factorizations=2)  # about 6 min
    with pytest.raises(NotImplementedError):
        synth.skip_unless_factorizable(
            "ecoinvent", pardiso=False, timeout=1800, factorizations=12
        )  # Monte Carlo with LCA


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
    synth.datapackages(s)
    assert not old.exists()
    assert fresh.exists()  # may still be another run's


# Properties of the tiered builder over the size and shape knobs, not two fixed seeds.
# Every example builds a system, so the cases are small: 20 to 400 products.
PROPERTY = settings(max_examples=200, deadline=None, suppress_health_check=[HealthCheck.too_slow])


@st.composite
def tiered(draw: st.DrawFn) -> System:
    return system(
        "smoke",
        seed=draw(st.integers(0, 2**32 - 1)),
        products=draw(st.integers(20, 400)),
        radius=draw(st.floats(0.1, 0.9)),
        back=draw(st.floats(0.0, 0.5)),
        units=draw(st.floats(0.0, 1.5)),
    )


@PROPERTY
@given(tiered())
def test_property_unit_diagonal_and_no_repeated_cells(s: System):
    assert np.allclose(s.technosphere().diagonal(), 1.0)
    cells = s.tech_rows * s.profile.products + s.tech_cols
    assert np.unique(cells).size == cells.size


@PROPERTY
@given(tiered())
def test_property_columns_sum_at_most_the_maximum_without_units(s: System):
    x = sparse.identity(s.profile.products) - s.technosphere()
    x0 = sparse.diags(1 / s.scale) @ x @ sparse.diags(s.scale)
    assert x0.min() >= 0
    assert abs(x0).sum(axis=0).max() <= MAX_COLUMN_SUM + 1e-12


def test_loopless_system_gets_its_radius_from_a_dense_solve():
    # No loops, so the matrix is nilpotent and ARPACK does not converge on it.
    s = system("smoke", seed=129, products=385, radius=0.5, back=0.0, units=0.0)
    x = sparse.identity(385) - s.technosphere()
    assert abs(sparse.diags(1 / s.scale) @ x @ sparse.diags(s.scale)).sum(axis=0).max() <= MAX_COLUMN_SUM + 1e-12


@PROPERTY
@given(tiered())
def test_property_reference_scores_equal_a_dense_solve(s: System):
    n = s.profile.products
    k = min(n, 30)
    supply = np.linalg.solve(s.technosphere().toarray(), np.eye(n, k))
    g = s.biosphere().toarray() @ supply
    dense = [[g[f - s.flow_offset, p] @ c for f, c in zip(s.cf_flows, s.cf_data, strict=True)] for p in range(k)]
    assert np.allclose(np.asarray(s.reference)[:k], dense, rtol=1e-9)
    assert np.min(dense) > 0


@PROPERTY
@given(tiered(), st.integers(0, 19))
def test_property_neumann_agrees_with_the_reference(s: System, product: int):
    demand = np.zeros(s.profile.products)
    demand[product] = 1.0
    cf = np.zeros(s.profile.flows)
    cf[s.cf_flows[0] - s.flow_offset] = s.cf_data[0]
    lca = types.SimpleNamespace(
        technosphere_matrix=s.technosphere(),
        demand_array=demand,
        biosphere_matrix=s.biosphere(),
        characterization_matrix=sparse.diags(cf),
    )
    assert neumann_score(lca, s.scale) == pytest.approx(s.reference[product][0], rel=1e-9)


# What system("smoke") builds under GENERATOR_VERSION "5". A builder change that moves the
# arrays fails here: bump GENERATOR_VERSION in synth.py and this pair together.
SMOKE_VERSION = "5"
SMOKE_SHA256 = "4ce0affb541cde364ae03ab8b9c88c396fcb9b682743c07bdd9e095e43d2220e"


def arrays_digest(s: System) -> str:
    """sha256 of the arrays, floats to 10 significant digits so a last-bit libm difference does not count."""
    h = hashlib.sha256()
    for ints in (s.tech_rows, s.tech_cols, s.tech_flip, s.bio_rows, s.bio_cols, *s.cf_flows):
        h.update(np.ascontiguousarray(ints, dtype="<i8").tobytes())
    for floats in (s.tech_data, s.bio_data, s.scale, *s.cf_data, np.asarray(s.reference)):
        h.update(" ".join(f"{v:.10g}" for v in np.ravel(floats)).encode())
    return h.hexdigest()


def test_smoke_arrays_match_the_generator_version():
    digest = arrays_digest(system("smoke"))
    assert (synth.GENERATOR_VERSION, digest) == (SMOKE_VERSION, SMOKE_SHA256), (
        f"system('smoke') now hashes to {digest} under GENERATOR_VERSION {synth.GENERATOR_VERSION!r}: "
        "if the builder changed, bump GENERATOR_VERSION in synth.py and set SMOKE_VERSION and SMOKE_SHA256 here"
    )


def test_the_random_builder_skips_sooner_than_the_tiered_one():
    # stress-random at 20k products: SuperLU takes about 5 min a factorization, the tiered rule said 1.
    with pytest.raises(NotImplementedError, match="stress-random"):
        synth.skip_unless_factorizable("stress-random", pardiso=False, timeout=600, factorizations=3)
    synth.skip_unless_factorizable("ecoinvent", pardiso=False, timeout=600, factorizations=3)  # about 9 min


def test_the_budget_is_the_case_timeout():
    with pytest.raises(NotImplementedError):  # about 12 min, past a 10-min case and under the old 15-min budget
        synth.skip_unless_factorizable("ecoinvent", pardiso=False, timeout=600, factorizations=4)
    synth.skip_unless_factorizable("ecoinvent", pardiso=False, timeout=900, factorizations=4)
