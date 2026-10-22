"""Group lookups must scale linearly in the number of resource groups.

bw_processing #113 (``Datapackage.groups``) and matrix_utils #48 (``filter_groups_for_packages``)
each removed a scan of every resource per group. The call counts of ``filter_by_attribute`` and
``has_relevant_data`` do not show it (one call per group, quadratic or not): what grows is the
number of resource fields each call reads. So the resources are dicts that count their reads.

The tests need Brightway, which never runs on the host, so they skip when it is absent. They run
in the box, and on the hosted runner in the ``scaling`` job of ``.github/workflows/python.yml``.
"""

# ruff: noqa: ANN401 - the Brightway objects are untyped here
from collections.abc import Callable
from typing import Any

import pytest

SMALL, LARGE = 1_000, 10_000
# Linear reads grow 10x from 1k to 10k groups, quadratic ones 100x. Anything under 20x is linear.
MAX_GROWTH = 20


class CountingDict(dict):
    """A resource that counts every field read, in one counter shared by all of them."""

    reads = 0

    def get(self, *args: Any) -> Any:
        CountingDict.reads += 1
        return super().get(*args)

    def __getitem__(self, key: str) -> Any:
        CountingDict.reads += 1
        return super().__getitem__(key)


def counted_groups(n: int) -> Any:
    from bwbench.synth import many_groups  # noqa: PLC0415 - imports numpy, which needs the conftest pin first

    dp: Any = many_groups(n)
    dp.resources = [CountingDict(r) for r in dp.resources]
    return dp


def growth(read: Callable[[Any], object]) -> float:
    """Resource reads at 10k groups over reads at 1k groups, for ``read(datapackage)``."""
    counts = []
    for n in (SMALL, LARGE):
        dp = counted_groups(n)
        CountingDict.reads = 0
        read(dp)
        counts.append(CountingDict.reads)
    return counts[1] / counts[0]


def test_groups_reads_resources_linearly():
    pytest.importorskip("bw_processing")
    g = growth(lambda dp: dp.groups)
    assert g < MAX_GROWTH, f"resource reads grew {g:.0f}x from 1k to 10k groups"


def test_has_relevant_data_reads_resources_linearly(monkeypatch: pytest.MonkeyPatch):
    pytest.importorskip("bw_processing")
    utils = pytest.importorskip("matrix_utils.utils")
    # Only the reads inside has_relevant_data count: a quadratic ``groups`` would otherwise
    # fail this test for bw_processing's fault.
    inside = 0
    real = utils.has_relevant_data

    def counting(*args: Any) -> Any:
        nonlocal inside
        before = CountingDict.reads
        try:
            return real(*args)
        finally:
            inside += CountingDict.reads - before

    monkeypatch.setattr(utils, "has_relevant_data", counting)

    def read(dp: Any) -> None:
        nonlocal inside
        inside = 0
        utils.filter_groups_for_packages(
            [dp], matrix_label="technosphere_matrix", use_vectors=True, use_arrays=False, use_distributions=False
        )
        CountingDict.reads = inside

    g = growth(read)
    assert g < MAX_GROWTH, f"resource reads grew {g:.0f}x from 1k to 10k groups"
