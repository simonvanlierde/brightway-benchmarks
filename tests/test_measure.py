import json

import numpy as np
import pytest
from scipy import sparse

from bwbench.synth import PROFILES_DIR, Stats, measure, system


def test_measure_a_known_matrix():
    # 0 <-> 1 is a loop, 2 feeds 0; product 1 is a waste treatment (production -1).
    a = sparse.csc_matrix(np.array([[1.0, -0.5, -0.2], [-0.4, -1.0, 0.0], [0.0, 0.0, 1.0]]))
    s = measure(a, locations=["CH", "CH", "DE"], sectors=["a", "b", "a"])
    assert s.products == 3
    assert s.entries == 3
    assert s.loops == {"components": 1, "largest": 2, "products_in_loops": 2}
    assert s.negative_input_share == pytest.approx(1 / 3)  # column 1 scaled by -1
    # X = [[0, -0.5, 0.2], [0.4, 0, 0], [0, 0, 0]]: eigenvalues of the loop are +-sqrt(-0.2)
    assert s.spectral_radius == pytest.approx(np.sqrt(0.2))
    assert s.spectral_radius_abs == pytest.approx(np.sqrt(0.2))
    assert s.same_location_share == pytest.approx(2 / 3)
    assert s.same_sector_share == pytest.approx(1 / 3)  # only 2 -> 0 stays in sector a
    assert s.inputs_per_product["q100"] == 1


def test_unknown_labels_are_left_out():
    a = sparse.csc_matrix(np.array([[1.0, -0.5, -0.2], [-0.4, -1.0, 0.0], [0.0, 0.0, 1.0]]))
    # Only input 2 -> 0 has both labels; 0 <-> 1 touches the unknown product 1.
    assert measure(a, sectors=["a", "", "a"]).same_sector_share == 1
    assert measure(a, sectors=["b", "", "a"]).same_sector_share == 0
    assert measure(a, sectors=["", "", ""]).same_sector_share is None


def test_measure_matches_the_generator_bounds():
    s = system("smoke")
    stats = measure(s.technosphere(), repeats=1)
    assert stats.products == s.profile.products
    assert "q100" not in stats.column_abs_sum  # one column's sum is a single value, never published
    assert stats.spectral_radius is not None
    assert stats.spectral_radius <= s.profile.radius + 1e-6
    assert stats.negative_input_share > 0
    assert set(stats.lu_fill) == {"COLAMD", "MMD_AT_PLUS_A"}
    assert measure(s.technosphere(), repeats=0).lu_fill == {}


def test_ecoinvent_profile_matches_its_target():
    """measure() as the oracle: the generated structure against ecoinvent 3.12 cut-off.

    LU fill is left out here (minutes per factorization at this size); it was checked when
    the profile was calibrated, as the profile's comment records.
    """
    s = system("ecoinvent")
    assert s.region is not None
    assert s.sector is not None
    got = measure(s.technosphere(), [str(r) for r in s.region], [str(r) for r in s.sector], repeats=0)
    want = Stats(**json.loads((PROFILES_DIR / "ecoinvent-3.12-cutoff.json").read_text())["stats"])
    assert got.products == want.products
    assert got.entries == pytest.approx(want.entries, rel=0.05)
    assert got.inputs_per_product["mean"] == pytest.approx(want.inputs_per_product["mean"], rel=0.05)
    assert abs(got.inputs_per_product["q50"] - want.inputs_per_product["q50"]) <= 1
    assert got.inputs_per_product["q99"] == pytest.approx(want.inputs_per_product["q99"], rel=0.3)
    for q in ("q25", "q50"):
        assert got.consumers_per_supplier[q] == want.consumers_per_supplier[q]
    for q in ("q90", "q99", "q100"):
        assert got.consumers_per_supplier[q] == pytest.approx(want.consumers_per_supplier[q], rel=0.3)
    share = got.loops["largest"] / got.products
    assert share == pytest.approx(want.loops["largest"] / want.products, abs=0.03)
    assert got.negative_input_share == pytest.approx(want.negative_input_share, abs=0.02)
    assert got.spectral_radius == pytest.approx(want.spectral_radius, abs=0.01)
    assert got.same_location_share == pytest.approx(want.same_location_share, abs=0.03)
    assert got.same_sector_share == pytest.approx(want.same_sector_share, abs=0.03)


def test_fill_drivers_on_a_known_matrix():
    # X has inputs 0 <- 1, 1 <- 0 (a reciprocated pair) and 0 <- 2; no triangle.
    a = sparse.csc_matrix(np.array([[1.0, -0.5, -0.2], [-0.4, -1.0, 0.0], [0.0, 0.0, 1.0]]))
    s = measure(a, repeats=1)
    assert s.reciprocity == pytest.approx(2 / 3)
    assert s.clustering == 0
    assert s.ata_fill == pytest.approx(9 / 6)  # row 0 joins all three columns in A^T A
    assert s.row_pairs == pytest.approx((9 + 4 + 1) / 6)  # rows hold 3, 2 and 1 entries
    assert s.core_after_hubs == 0  # without product 0, nothing has two neighbours
    assert s.dense_rows == {"cutoff": 17, "above": 0, "half_to_cutoff": 0}  # max(16, 10 sqrt(3))
    assert s.off_diagonal_pivots == {"COLAMD": 0.0, "MMD_AT_PLUS_A": 0.0}  # diagonally dominant


def test_a_triangle_is_clustered_and_a_small_diagonal_is_pivoted():
    triangle = sparse.csc_matrix(np.array([[1.0, -0.1, -0.1], [-0.1, 1.0, -0.1], [-0.1, -0.1, 1.0]]))
    assert measure(triangle, repeats=0).clustering == 1
    # Column 0's diagonal (1) is smaller than its other entry (10): partial pivoting swaps them.
    a = sparse.csc_matrix(np.array([[1.0, 1.0], [10.0, 1.0]]))
    s = measure(a, repeats=1)
    assert s.off_diagonal_pivots is not None
    assert s.off_diagonal_pivots["COLAMD"] > 0
    assert s.lu_fill_no_pivoting is not None
    assert set(s.lu_fill_no_pivoting) == {"COLAMD", "MMD_AT_PLUS_A"}
