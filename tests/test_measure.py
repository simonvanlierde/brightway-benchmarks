import json

import numpy as np
import pytest
from scipy import sparse
from scipy.sparse import linalg as sla

from bwbench import synth
from bwbench.synth import PROFILES_DIR, Stats, measure, system


def test_measure_refuses_a_product_without_net_production():
    with pytest.raises(ValueError, match="nonzero net production"):
        measure(sparse.csc_matrix(np.array([[1.0, 0.5], [0.2, 0.0]])))


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
    assert "q100" not in s.inputs_per_product  # one dataset's count, never published


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
    assert set(stats.lu_fill) == {"COLAMD", "MMD_AT_PLUS_A", "COLAMD (A^T)", "MMD_AT_PLUS_A (A^T)"}
    assert set(stats.factor_seconds) == set(stats.lu_fill)
    # The (A^T) keys really factorize the transpose of the column-normalized matrix.
    a = sparse.csc_matrix(s.technosphere(), dtype=np.float64)
    at = (a @ sparse.diags(1.0 / a.diagonal())).T.tocsc()
    lu = sla.splu(at, permc_spec="COLAMD")
    assert stats.lu_fill["COLAMD (A^T)"] == pytest.approx((lu.L.nnz + lu.U.nnz - at.shape[0]) / at.nnz)
    assert stats.lu_fill["COLAMD (A^T)"] != pytest.approx(stats.lu_fill["COLAMD"])
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
    assert got.inputs_per_product["q90"] == pytest.approx(want.inputs_per_product["q90"], rel=0.1)
    assert abs(got.inputs_per_product["q50"] - want.inputs_per_product["q50"]) <= 1
    assert got.inputs_per_product["q99"] == pytest.approx(want.inputs_per_product["q99"], rel=0.3)
    for q in ("q25", "q50"):
        assert got.consumers_per_supplier[q] == want.consumers_per_supplier[q]
    for q in ("q90", "q99"):
        assert got.consumers_per_supplier[q] == pytest.approx(want.consumers_per_supplier[q], rel=0.3)
    share = got.loops["largest"] / got.products
    # Seed 0 only: over 64 seeds the giant loop's share is 0.664 +- 0.042 (0.57 to 0.74), so this
    # band is tighter than one realization; seed 0 is typical (z -1.1). Other seeds need +-0.1.
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
    # Rows {0, 1, 2}, {0, 1} and {2} pairwise: Jaccard 2/3, 1/3 and 0.
    assert s.hub_jaccard == pytest.approx((2 / 3 + 1 / 3 + 0) / 3)
    # Rows 0 and 1 (3 and 2 entries) fall in the 2-4 band; together they join 9 column pairs.
    band = {"overlap": pytest.approx(9 / 13), "pairs_share": pytest.approx(13 / 14), "suppliers_shared": 4 / 3}
    assert s.overlap_by_band == {"2-4": band}  # pairs (0, 1), (0, 2), (1, 2) share 2, 1 and 1 suppliers
    labelled = measure(a, locations=["CH", "CH", "DE"], sectors=["a", "b", "a"], repeats=0)
    assert labelled.overlap_by_band is not None
    assert labelled.overlap_by_band["2-4"]["same_location"] == pytest.approx(1 / 3)
    assert labelled.overlap_by_band["2-4"]["same_sector"] == pytest.approx(1 / 3)
    assert s.copied_inputs == pytest.approx(2 / 3)  # products 1 and 2 both take in product 0 only
    # Without product 0's row (the top 1%), rows {0, 1} and {2} share no pair: no overlap.
    assert s.overlap_without_hubs == pytest.approx(1.0)

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


def test_overlap_without_hubs_drops_the_hub_rows():
    # 200 products; product 0 supplies all of them, products 1-9 each supply the same 20.
    n = 200
    a = sparse.lil_matrix(np.eye(n))
    a[0, 1:] = -0.001
    for i in range(1, 10):
        a[i, 100:120] = -0.001
    s = measure(a.tocsc(), repeats=0)
    # The two largest rows (1% of 200) go: product 0 and product 1. Rows 2-9 (their diagonal plus
    # the same 20 consumers) share the 400 pairs among those 20; each adds 41 pairs of its own;
    # the 190 diagonal-only rows add 170 pairs not already counted.
    assert s.overlap_without_hubs == pytest.approx((400 + 8 * 41 + 170) / (8 * 21**2 + 190))


def test_hub_jaccard_stays_finite_with_empty_rows():
    a = sparse.csc_matrix(np.diag([1.0, 1.0, 1.0, 1.0]))  # every row holds only its diagonal
    s = measure(a, repeats=0)
    assert s.hub_jaccard is not None
    assert np.isfinite(s.hub_jaccard)


def test_overlap_bands_include_both_ends_and_label_the_last_one_open(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(synth, "OVERLAP_BANDS", ((2, 3), (4, 1 << 62)))
    # Rows 0, 1 and 2 hold 4, 3 and 2 entries (their diagonal included); row 3 holds 1.
    a = sparse.lil_matrix(np.eye(4))
    a[0, 1:4] = -0.1
    a[1, 2:4] = -0.1
    a[2, 3] = -0.1
    s = measure(a.tocsc(), repeats=0)
    assert s.overlap_by_band is not None
    assert set(s.overlap_by_band) == {"2-3", "4+"}
    assert sum(b["pairs_share"] for b in s.overlap_by_band.values()) == pytest.approx(1 - 1 / (16 + 9 + 4 + 1))


def test_lu_fill_of_the_identity_is_one():
    # L and U are both the identity: 4 + 4 entries, the diagonal counted once, over nnz(A) = 4.
    assert set(measure(sparse.csc_matrix(np.eye(4)), repeats=1).lu_fill.values()) == {1.0}


def test_column_sums_are_over_columns_not_rows():
    # X has column sums 0, 0.5 and 0.25; its row sums are 0.75, 0 and 0.
    a = sparse.csc_matrix(np.array([[1.0, -0.5, -0.25], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]))
    sums = measure(a, repeats=0).column_abs_sum
    want = {"q10": 0.05, "q25": 0.125, "q50": 0.25, "q75": 0.375, "q90": 0.45, "q99": 0.495}
    assert sums == pytest.approx(want)


def test_dense_rows_count_the_hub_and_the_half_hub_rows():
    n = 400  # cutoff max(16, int(10 * 20)) = 200, half 100; row counts include the diagonal
    a = sparse.lil_matrix(np.eye(n))
    a[0, 1:250] = -0.001  # 250 entries: above
    a[1, 2:151] = -0.001  # 150: between
    a[2, 3:202] = -0.001  # 200: exactly the cutoff, so not above
    a[3, 4:103] = -0.001  # 100: exactly half, so not between
    s = measure(a.tocsc(), repeats=0)
    assert s.dense_rows == {"cutoff": 200, "above": 1, "half_to_cutoff": 2}


def test_core_after_hubs_keeps_a_cycle_but_not_the_hub():
    n = 100  # the top 1% by degree is one product: the hub, product 0
    a = sparse.lil_matrix(np.eye(n))
    a[0, 1:] = -0.01
    for i, j in ((1, 2), (2, 3), (3, 4), (4, 1)):  # a 4-cycle, each also linked to the hub
        a[i, j] = -0.1
    s = measure(a.tocsc(), repeats=0)
    assert s.core_after_hubs == pytest.approx(4 / n)  # the pendants peel off; the hub is removed first


def test_copied_inputs_counts_only_products_with_inputs():
    # Products 1 and 2 take in product 0 only, product 3 takes in 0 and 1; 0 and 4 take in nothing.
    a = sparse.lil_matrix(np.eye(5))
    a[0, 1] = a[0, 2] = a[0, 3] = a[1, 3] = -0.1
    assert measure(a.tocsc(), repeats=0).copied_inputs == pytest.approx(2 / 3)


def test_spectral_radius_branches(monkeypatch: pytest.MonkeyPatch):
    assert synth.spectral_radius(sparse.csc_matrix((5, 5))) == 0.0
    # n < 3 is dense: eigenvalues 0.5 +- 2i.
    small = sparse.csc_matrix(np.array([[0.5, 2.0], [-2.0, 0.5]]))
    assert synth.spectral_radius(small) == pytest.approx(np.sqrt(4.25))
    assert synth.spectral_radius(sparse.csc_matrix(np.diag([1.0, -2.0, 3.0]))) == pytest.approx(3.0)

    def no_convergence(*_args: object, **_kwargs: object):
        msg = "stuck"
        raise sla.ArpackNoConvergence(msg, np.array([]), np.array([]))

    monkeypatch.setattr(sla, "eigs", no_convergence)
    assert synth.spectral_radius(sparse.csc_matrix(np.diag([1.0, 2.0, 3.0]))) is None
    assert synth.spectral_radius(small) == pytest.approx(np.sqrt(4.25))  # the dense branch never calls eigs
