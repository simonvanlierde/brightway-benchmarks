import math

import pytest

from bwbench import DIRECT_RTOL, check


def test_check_returns_the_relative_error():
    assert check(1.0 + 1e-12, 1.0, DIRECT_RTOL) == pytest.approx(1e-12)
    assert check(-2.0, -2.0, DIRECT_RTOL) == 0


@pytest.mark.parametrize("score", [1.0 + 1e-6, -1.0, math.nan])
def test_check_raises_above_the_tolerance(score: float):
    with pytest.raises(AssertionError, match="relative error"):
        check(score, 1.0, DIRECT_RTOL)
