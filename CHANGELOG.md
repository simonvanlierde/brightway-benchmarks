# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this
project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- asv suites for bw2calc, bw2data, bw_processing, matrix_utils, bw_graph_tools and bw_timex,
  run over their released versions. Every case except bw_processing's two `EntriesPath`
  cases checks its result against a float64 reference.
- A seeded generator of synthetic LCA systems, `system(profile, seed=..., **overrides)`,
  written as bw_processing datapackages or bw2data databases. The `ecoinvent` profile copies
  the structure of ecoinvent 3.12 cut-off: loops, hub suppliers, region and sector locality,
  waste treatments and per-product units. `smoke`, `mc100k` and `regional` scale it to 200,
  100k and 250k products. `exiobase` and `stress-random` use a random structure.
- `measure()`, the structural statistics of a technosphere matrix. It calibrates and checks
  the generator, and reports what drives LU fill: rows near COLAMD's dense cut-off,
  nnz(AᵀA), clustering, reciprocity, the 2-core left without hubs, and fill and pivots without
  partial pivoting.
- `@bench`: write a benchmark once, as a setup that returns the timed call and its check,
  and run it under asv or pytest-codspeed. A setup that needs a teardown yields instead.
- Next to each machine's results: a PEP 751 lock file per asv environment, and an RO-Crate
  `ro-crate-metadata.json` that names the bwbench commit, the generator version and the
  profiles.
- A comparison of a bw2data SQLite project with the Parquet registry of bw2data #290.
- `just smoke`, `just bench`, `just site` and `just registry-vs-sqlite`. Each runs in a
  throwaway container.
- A weekly smoke run in CI.
- Skips, with the upstream link, for bw2calc cases that a release crashes on for a reported
  reason: `IterativeLCA`'s second solve where scipy rejects `atol="legacy"`, and
  `FastScoresOnlyMultiLCA` and `JacobiGMRESLCA` Monte Carlo with PyPardiso (bw2calc #157).
  A release with the fix runs them again.
- A warning when numpy is imported before `bwbench`, because the BLAS thread pin then comes
  too late.

[Unreleased]: https://github.com/simonvanlierde/brightway-benchmarks/commits/HEAD
