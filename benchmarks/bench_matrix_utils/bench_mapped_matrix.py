"""matrix_utils: building a MappedMatrix from a datapackage with many resource groups.

The fixed stack uses bw_processing 2.0 across all timed matrix_utils releases.
"""

import matrix_utils as mu

from bwbench import group_counts
from bwbench.asv import classes
from bwbench.bench import UNCHECKED, BenchSetup, bench
from bwbench.synth import many_groups


@bench({"groups": group_counts()}, asv="MappedMatrixBuild", timeout=600)
def mapped_matrix(groups: int) -> BenchSetup:
    dp = many_groups(groups)
    m = mu.MappedMatrix(packages=[dp], matrix="technosphere_matrix").matrix
    if m.nnz != groups or not (m.diagonal() == 1).all():
        raise AssertionError("matrix does not hold one diagonal entry of 1 per group")
    return lambda: mu.MappedMatrix(packages=[dp], matrix="technosphere_matrix"), UNCHECKED


classes(__name__)
