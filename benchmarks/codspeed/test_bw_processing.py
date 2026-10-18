"""pytest-codspeed entry for the bw_processing suite: `just codspeed bw_processing`."""

# The package import pins the BLAS threads before numpy loads.
from bench_bw_processing.bench_datapackage import *  # noqa: F403

import bwbench.pytest

# Called through the module: a bare `tests` name would itself be collected as a test.
bwbench.pytest.tests(globals())
