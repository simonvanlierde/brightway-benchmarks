"""matrix_utils: building a MappedMatrix from a datapackage with many resource groups.

``filter_groups_for_packages`` checked every group against the whole package, so this
is quadratic in groups (PR #48; 4.32 s to 0.030 s at 16k groups with bw_processing #113
installed, 45.8 s to 3.0 s for both PRs together).
"""

import matrix_utils as mu

from bwbench import knob
from bwbench.synth import many_groups


class MappedMatrixBuild:
    params = ([int(x) for x in knob("groups", "100,1000")],)
    param_names = ["groups"]
    timeout = 600

    def setup(self, groups: int) -> None:
        self.dp = many_groups(groups)
        m = mu.MappedMatrix(packages=[self.dp], matrix="technosphere_matrix").matrix
        if m.nnz != groups or not (m.diagonal() == 1).all():
            raise AssertionError("matrix does not hold one diagonal entry of 1 per group")

    def time_mapped_matrix(self, groups: int) -> None:
        mu.MappedMatrix(packages=[self.dp], matrix="technosphere_matrix")
