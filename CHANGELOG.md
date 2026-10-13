# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this
project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

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

- Reference scores come from a Neumann series instead of SuperLU, for products 0 to 29.
- Cached systems are keyed on everything that shapes them, so caches from earlier
  checkouts are no longer used. `BWBENCH_DATA` and `BWBENCH_IMAGE` are gone.
- Smoke results go to `.asv/smoke/`, and results are labelled with the container
  hostname unless `BWBENCH_MACHINE` is set.

[Unreleased]: https://github.com/simonvanlierde/brightway-benchmarks/commits/HEAD
