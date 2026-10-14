import pytest

import bwbench  # before any test module loads numpy, so the BLAS thread pin lands


@pytest.fixture(autouse=True)
def _forget_first_times() -> None:
    """`bwbench.first_time` remembers keys for the whole process; each test starts fresh."""
    bwbench._SEEN.clear()  # noqa: SLF001
