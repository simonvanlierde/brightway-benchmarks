import math
import subprocess
import sys

import pytest

from bwbench import DIRECT_RTOL, check, check_table
from bwbench.synth import system


def test_check_returns_the_relative_error():
    assert check(1.0 + 1e-12, 1.0, DIRECT_RTOL) == pytest.approx(1e-12)
    assert check(-2.0, -2.0, DIRECT_RTOL) == 0


@pytest.mark.parametrize("score", [1.0 + 1e-6, -1.0, math.nan])
def test_check_raises_above_the_tolerance(score: float):
    with pytest.raises(AssertionError, match="relative error"):
        check(score, 1.0, DIRECT_RTOL)


def test_check_table_catches_swapped_demands():
    refs = system("smoke").reference
    assert check_table(refs, refs, DIRECT_RTOL) == 0
    swapped = [refs[1], refs[0], *refs[2:]]
    with pytest.raises(AssertionError, match=r"\[0\]\[0\]"):
        check_table(swapped, refs, DIRECT_RTOL)
    with pytest.raises(AssertionError, match="rows"):
        check_table(refs[:3], refs[:4], DIRECT_RTOL)


@pytest.mark.skipif(sys.platform != "linux", reason="the inherited high-water mark is a Linux kernel trait")
def test_peak_rss_bytes_in_a_child_is_its_own_not_its_parents():
    block = bytearray(200_000_000)
    block[::4096] = b"x" * len(block[::4096])  # touch every page
    code = "from bwbench import peak_rss_bytes; print(peak_rss_bytes())"
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert 1_000_000 < int(out.stdout) < 100_000_000
