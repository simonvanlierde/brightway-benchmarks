"""pytest-codspeed entry for the bw2data suite: `just codspeed bw2data`."""

# The package import pins the BLAS threads before numpy loads.
from bench_bw2data.bench_write import *  # noqa: F403

import bwbench.pytest

# Called through the module: a bare `tests` name would itself be collected as a test.
bwbench.pytest.tests(globals())
