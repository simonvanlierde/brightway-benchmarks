"""pytest-codspeed entry for the bw2calc suite: `just codspeed bw2calc`."""

# The package import pins the BLAS threads before numpy loads.
from bench_bw2calc.bench_lca import *  # noqa: F403

import bwbench.pytest

# Called through the module: a bare `tests` name would itself be collected as a test.
bwbench.pytest.tests(globals())
