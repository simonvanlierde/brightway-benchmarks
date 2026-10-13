"""matrix_utils: building a MappedMatrix from a datapackage with many resource groups.

``filter_groups_for_packages`` checked every group against the whole package, so this
is quadratic in groups (PR #48; 4.32 s to 0.030 s at 16k groups with bw_processing #113
installed, 45.8 s to 3.0 s for both PRs together). bw_processing's own ``groups`` is
quadratic too until #113, and dominates the build, so asv/matrix_utils.json runs every
commit against bw_processing 1.6 and against the #113 head (1a6f898). No release has #48
yet, so the config also benchmarks its head (7335e8a), as the branch ``pull/48/head``.
"""

import matrix_utils as mu

from bwbench import knob
from bwbench.asv import classes
from bwbench.bench import UNCHECKED, BenchSetup, bench
from bwbench.synth import many_groups


@bench({"groups": knob("groups", "100,1000", int)}, asv="MappedMatrixBuild", timeout=600)
def mapped_matrix(groups: int) -> BenchSetup:
    dp = many_groups(groups)
    m = mu.MappedMatrix(packages=[dp], matrix="technosphere_matrix").matrix
    if m.nnz != groups or not (m.diagonal() == 1).all():
        raise AssertionError("matrix does not hold one diagonal entry of 1 per group")
    return lambda: mu.MappedMatrix(packages=[dp], matrix="technosphere_matrix"), UNCHECKED


classes(__name__)
