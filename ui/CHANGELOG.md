# Changelog

All notable changes to the benchmark UI are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this
project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Home shows a tested setup for your platform, with its installation files, measured solver alternatives and the latest release changes ([viewer](README.md#what-it-shows)).
- A Compatibility page lists every check by platform and Python version, with the last environment that passed.
- Each page has its own shareable URL, and old benchmark links and homepage anchors still work.
- Search benchmarks by name, and filter release changes by package and direction.
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
- Change tables reflow into labelled rows on phones.

### Fixed

- Opening a change keeps the machine that measured it, and narrow charts keep their first and last release labels.
- A link to an unknown benchmark says how to find it.
