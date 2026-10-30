# Changelog

All notable changes to the benchmark UI are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this
project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- A JSON Schema for the data: an index (format version 1) and reports in Bencher Metric
  Format v0.
- `src/lib/contract.ts` loads both from a configurable URL and checks them against the schema
  and each other.
- The maintainer view: each benchmark's history over its releases, one line per environment,
  with its parameters, measure and machine picked from the data and kept in the URL. Changes the
  data lists are marked on the chart and listed below it, and a data table holds every value.
- A start page listing what moved beyond its noise in each package's latest release.
- The chart can be read with the keyboard and downloaded as SVG; the site has light and dark
  themes, fits a phone, and is checked against WCAG 2.2 AA in browser tests.
- `changes` in the index (optional, so `format_version` stays 1): where a series moved, by
  release against its noise or as a change point.
