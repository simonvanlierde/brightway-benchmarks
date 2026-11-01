# Changelog

All notable changes to the benchmark UI are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this
project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Home leads with a tested platform setup, saved package versions and installation files, measured solver alternatives, and both regressions and improvements. Compatibility exposes platform and Python filters, check coverage and current results beside dated last-passing environments ([viewer](README.md#what-it-shows)).
- Home, Compatibility, Release changes and Benchmark explorer have dedicated navigation and shareable URLs. Existing benchmark links and the compatibility anchor still work; missing guidance leaves histories available ([viewer](README.md#what-it-shows)).
- Search benchmarks by readable name or original identifier. Filter latest changes by package and direction, with counts scoped to the selected package and shareable filter URLs ([viewer](README.md#what-it-shows)).
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

- The viewer separates its searchable catalogue from the evidence workspace, with clearer hierarchy and chart colours distinct from release-change status. Change tables reflow into labelled rows on phones ([viewer](README.md#what-it-shows)).

### Fixed

- Opening a change keeps the machine that produced it; multi-machine rows identify that machine. Narrow charts keep their first and last release labels within the tick budget ([viewer](README.md#what-it-shows)).
- Unknown benchmark links explain how to recover ([viewer](README.md#what-it-shows)).
