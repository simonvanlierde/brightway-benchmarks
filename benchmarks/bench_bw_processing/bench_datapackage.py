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
from bwbench.asv import classes
from bwbench.bench import UNCHECKED, BenchSetup, bench
from bwbench.synth import many_groups

GROUPS = {"groups": knob("groups", "100,1000", int)}
ENTRIES = {"entries": knob("entries", "10000,100000", int)}


@bench(GROUPS, asv="Groups", timeout=600)
def groups(groups: int) -> BenchSetup:
    dp = many_groups(groups)
    if len(dp.groups) != groups:
        raise AssertionError("wrong group count")
    return lambda: dp.groups, UNCHECKED


def matrix_entries(entries: int) -> list:
    if not hasattr(bwp, "MatrixEntry"):
        raise NotImplementedError(f"bw_processing {bwp.__version__} has no MatrixEntry")
    rng = np.random.default_rng(0)
    rows = rng.integers(0, 10_000, entries)
    return [bwp.MatrixEntry(row=int(r), col=i, amount=1.0) for i, r in enumerate(rows)]


@bench(ENTRIES, asv="EntriesPath", timeout=600)
def add_entries(entries: int) -> BenchSetup:
    found = matrix_entries(entries)

    def run() -> None:
        bwp.create_datapackage().add_entries(matrix="technosphere_matrix", entries=found)

    return run, UNCHECKED


@bench(ENTRIES, asv="EntriesPath", timeout=600)
def vars_iterator(entries: int) -> BenchSetup:
    found = matrix_entries(entries)

    def run() -> None:
        bwp.create_datapackage().add_persistent_vector_from_iterator(
            matrix="technosphere_matrix",
            dict_iterator=(dict(vars(e)) for e in found),
            nrows=len(found),
        )

    return run, UNCHECKED


classes(__name__)
