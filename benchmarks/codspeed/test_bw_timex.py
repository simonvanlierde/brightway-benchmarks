"""pytest-codspeed entry for the bw_timex suite: `just codspeed bw_timex`."""

# The package import pins the BLAS threads before numpy loads.
from bench_bw_timex.bench_timex import *  # noqa: F403

import bwbench.pytest

# Called through the module: a bare `tests` name would itself be collected as a test.
bwbench.pytest.tests(globals())
