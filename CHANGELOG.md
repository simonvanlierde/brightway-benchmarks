# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this
project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- A tiered generator calibrated to the structure of ecoinvent 3.12 cut-off: supply-chain
  order with loops, hub suppliers, region and sector locality, waste treatments (negative
  inputs) and per-product units. `system(profile, seed=..., **overrides)` builds one;
  `measure()` checks it against the measured statistics.
- `@bench`: each benchmark is one setup function returning the timed call and its check, run
  under asv (`bwbench.asv.classes`) or pytest-codspeed (`bwbench.pytest.tests`). A setup that
  needs a teardown yields instead of returning. asv names stay as they were.
- Next to each machine's results: a PEP 751 `pylock.<env>.toml` per asv environment, with
  every package's index URL and hashes, and an RO-Crate `ro-crate-metadata.json` naming the
  bwbench commit, the generator version and the profiles.
- A warning when numpy is imported before `bwbench`, whose BLAS thread pin would then come
  too late.

- A seeded generator of synthetic LCA systems, written as bw_processing datapackages or
  as bw2data databases, at smoke, ecoinvent, EXIOBASE, 100k and 250k-product sizes.
- asv suites for bw2calc, bw2data, bw_processing, matrix_utils, bw_graph_tools and
  bw_timex over their released versions. Every case except bw_processing's
  `add_entries` checks its result.
- A comparison of a bw2data SQLite project with the Parquet registry of bw2data #290.
- `just smoke`, `just bench`, `just site` and `just registry-vs-sqlite`, all run in a
  throwaway container that sees the repo read-only.
- A weekly smoke run in CI.
- bw2calc cases that a release crashes on for an already reported reason are skipped with
  the link: `IterativeLCA`'s second solve where scipy rejects `atol="legacy"`, and
  `FastScoresOnlyMultiLCA` and `JacobiGMRESLCA` Monte Carlo with PyPardiso (bw2calc #157).
  A release with the fix runs them again.

### Changed

- **Breaking:** profiles replace sizes. `smoke`, `ecoinvent`, `mc100k` and `regional` use the
  tiered generator; `exiobase` and the new `stress-random` keep the random one. The generator
  version is 3, so earlier results and cached systems are not reused.
- The bw_processing and matrix_utils cases time one call per setup, like the others, instead
  of asv's automatic count.
- The Neumann reference stops on a bound of the rest of the series, valid up to column sums
  near 1, instead of a rule that held only up to 0.5.

- asv installs each benchmarked commit without touching its dependencies, so the pins in
  `matrix.req` and the bw_processing #113 build in the matrix_utils config stay installed.
  asv's default `--force-reinstall` put PyPI's bw_processing 1.6 back in place of #113.
- Reference scores come from a Neumann series instead of SuperLU, for products 0 to 29.
- Cached systems are keyed on everything that shapes them, so caches from earlier
  checkouts are no longer used. `BWBENCH_DATA` and `BWBENCH_IMAGE` are gone.
- Smoke results go to `.asv/smoke/`, and results are labelled with the container
  hostname unless `BWBENCH_MACHINE` is set.

[Unreleased]: https://github.com/simonvanlierde/brightway-benchmarks/commits/HEAD
