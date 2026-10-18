"""pytest-codspeed entry for the matrix_utils suite: `just codspeed matrix_utils`."""

# The package import pins the BLAS threads before numpy loads.
from bench_matrix_utils.bench_mapped_matrix import *  # noqa: F403

import bwbench.pytest

# Called through the module: a bare `tests` name would itself be collected as a test.
bwbench.pytest.tests(globals())
