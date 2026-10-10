# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this
project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- A seeded generator of synthetic LCA systems, written as bw_processing datapackages or
  as bw2data databases, at smoke, ecoinvent, EXIOBASE, 100k and 250k-product sizes.
- asv suites for bw2calc, bw2data, bw_processing, matrix_utils, bw_graph_tools and
  bw_timex over their released versions, each timing with a correctness check beside it.
- A comparison of a bw2data SQLite project with the Parquet registry of bw2data #290.
- `just smoke`, `just bench`, `just site` and `just registry-vs-sqlite`, all run in a
  throwaway container.

[Unreleased]: https://github.com/simonvanlierde/brightway-benchmarks/commits/HEAD
