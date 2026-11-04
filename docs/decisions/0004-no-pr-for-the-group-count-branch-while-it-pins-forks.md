# 0004. No PR for the group-count branch while it pins fork commits

- Status: accepted
- Date: 2026-10-23

## Context

The branch `feat/group-scaling` adds group-count scaling cells. A guard counts resource-field reads from 1,000 to 10,000 groups and asserts the growth stays under 20 times. The `Groups` and `MappedMatrixBuild` cells stretch to 16,000 groups through `BWBENCH_GROUPS`.

The branch pins commits from forks of the Brightway packages, including `pull/113/head` of bw_processing. It depends on two open upstream pull requests:

- [brightway-lca/bw_processing#113](https://github.com/brightway-lca/bw_processing/pull/113), "perf: build resource groups in one pass".
- [brightway-lca/matrix_utils#48](https://github.com/brightway-lca/matrix_utils/pull/48), "perf: check each group for relevant data on its own resources".

As of 2026-11-04 both are open and unmerged. Both were last updated on 2026-10-28.

## Decision

The branch gets no pull request while it pins fork commits. After both upstream pull requests merge, drop the branch entry and the pins, rebase, then open the pull request.

## Consequences

- The branch stays on origin as a backup. It is not on main.
- The group-count cells wait for the upstream merges.
- Re-check both upstream pull requests when the waiting upstream items are reviewed.
