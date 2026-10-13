import numpy as np
import pytest
from scipy import sparse

from bwbench.synth import SIZES, generate, measure


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
    system = generate(SIZES["smoke"])
    s = measure(system.technosphere())
    assert s.products == SIZES["smoke"].products
    assert s.column_abs_sum["q99"] < 0.5
    assert "q100" not in s.column_abs_sum  # one column's sum is a single value, never published
    assert s.spectral_radius is not None
    assert s.spectral_radius < 0.5
    assert s.negative_input_share == 0
