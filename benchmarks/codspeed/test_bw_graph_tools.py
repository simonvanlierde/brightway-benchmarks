"""pytest-codspeed entry for the bw_graph_tools suite: `just codspeed bw_graph_tools`."""

# The package import pins the BLAS threads before numpy loads.
from bench_bw_graph_tools.bench_traversal import *  # noqa: F403

import bwbench.pytest

# Called through the module: a bare `tests` name would itself be collected as a test.
bwbench.pytest.tests(globals())
