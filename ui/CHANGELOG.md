# Changelog

All notable changes to the benchmark UI are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this
project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Two pages, Setup and Benchmarks, with a benchmark search in the masthead ([viewer](README.md#what-it-shows)).
- Setup gives an install command for uv, pip, conda or pixi, pinned to a dated set that does not change, with a link that copies the newest one.
- Setup lists every check by platform and Python version in a grid; select one to install its set.
- Setup and Benchmarks show curated findings, each linked to the chart behind it.
- Each page has its own shareable URL, and old benchmark links and homepage anchors still work.
- Search benchmarks by name, and filter release changes by package and direction.
- Release changes lists regressions first, with improvements grouped by benchmark.
- A chart's legend buttons bring one environment forward.
- Benchmarks opens on the findings and the latest release changes, each change with a small history line.
- A benchmark explains each parameter under its control, and links its values, solvers and source to their documentation.
- Setup says which machine timed the solvers, and notes when that is not your platform.
- Setup lists a failing check on your platform, such as an upstream test suite, before the install command, and the command has a copy button.
- Charts with three releases or fewer set environments a little apart, and commits that are not releases draw faint, with a count under the chart.
- The explorer explains each benchmark, its parameters and the values you choose, such as what `JacobiGMRESLCA` does.
- A JSON Schema for the data: an index (format version 1) and reports in Bencher Metric
  Format v0.
- `src/lib/contract.ts` loads both from a configurable URL and checks them against the schema
  and each other.
- The maintainer view: each benchmark's history over its releases, one line per environment,
  with its parameters, measure and machine picked from the data and kept in the URL. Changes the
  data lists are marked on the chart and listed below it, and a data table holds every value.
- A start page listing what moved beyond its noise in each package's latest release, worse first.
- The chart can be read with the keyboard and downloaded as SVG; the site has light and dark
  themes, fits a phone, and is checked against WCAG 2.2 AA in browser tests.
- `changes` in the index (optional, so `format_version` stays 1): where a series moved, by
  release against its noise or as a change point.
- Optional `label` on environments and `bounds` on measures in the index: the name to show for
  an environment, and what a metric's lower and upper values are.

### Changed

- A new flat blue look, with red and teal kept for worse and better results ([design](../DESIGN.md)).
- Change tables reflow into labelled rows on phones, and no text is smaller than 12px.

### Fixed

- Setup shows test results and coverage before Copy, and offers optional instructions for a new uv project ([viewer](README.md#what-it-shows)).
- Phones show checks for the selected platform and collapse longer parameter explanations. Desktop check grids indicate hidden columns ([viewer](README.md#what-it-shows)).
- Benchmark search keeps keyboard focus while typing and shows matches on phones ([viewer](README.md#what-it-shows)).
- Release-change history lines keep each package's commits separate, and benchmark explanations meet the 12px minimum text size ([viewer](README.md#what-it-shows)).
- Opening a change keeps the machine that measured it, and narrow charts keep their first and last release labels.
- A link to an unknown benchmark says how to find it.
