"""bw_processing: group lookup and the MatrixEntry path.

``groups`` calls ``filter_by_attribute`` once per label, so it is quadratic in the
number of resource groups (PR #113 makes it one pass: 36.4 s to 0.021 s at 16k groups).
Issue #111 measures ``MatrixEntry.as_dict`` at 1.87 us per entry against 0.22 us for
``dict(vars(entry))``; the two ``EntriesPath`` cases time ``add_entries`` against that
cheaper conversion through the same public iterator method.
"""

import bw_processing as bwp
import numpy as np

from bwbench import knob


def many_groups(n: int) -> object:
    """An in-memory datapackage with ``n`` one-entry resource groups."""
    dp = bwp.create_datapackage()
    for i in range(n):
        idx = np.array([(i, i)], dtype=bwp.INDICES_DTYPE)
        dp.add_persistent_vector(matrix="technosphere_matrix", name=f"g{i}", indices_array=idx, data_array=np.ones(1))
    return dp


class Groups:
    params = ([int(x) for x in knob("groups", "100,1000")],)
    param_names = ["groups"]
    timeout = 600

    def setup(self, groups: int) -> None:
        self.dp = many_groups(groups)
        if len(self.dp.groups) != groups:
            raise AssertionError("wrong group count")

    def time_groups(self, groups: int) -> None:
        self.dp.groups  # noqa: B018 - the property is the work


class EntriesPath:
    params = ([int(x) for x in knob("entries", "10000,100000")],)
    param_names = ["entries"]
    timeout = 600

    def setup(self, entries: int) -> None:
        if not hasattr(bwp, "MatrixEntry"):
            raise NotImplementedError(f"bw_processing {bwp.__version__} has no MatrixEntry")
        rng = np.random.default_rng(0)
        rows = rng.integers(0, 10_000, entries)
        self.entries = [bwp.MatrixEntry(row=int(r), col=i, amount=1.0) for i, r in enumerate(rows)]

    def time_add_entries(self, entries: int) -> None:
        bwp.create_datapackage().add_entries(matrix="technosphere_matrix", entries=self.entries)

    def time_vars_iterator(self, entries: int) -> None:
        bwp.create_datapackage().add_persistent_vector_from_iterator(
            matrix="technosphere_matrix",
            dict_iterator=(dict(vars(e)) for e in self.entries),
            nrows=len(self.entries),
        )
