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


def test_measure_matches_the_generator_bounds():
    system = generate(SIZES["smoke"])
    s = measure(system.technosphere())
    assert s.products == SIZES["smoke"].products
    assert s.column_abs_sum["q100"] < 0.5
    assert s.spectral_radius < 0.5
    assert s.negative_input_share == 0
