# Changelog

All notable changes to the benchmark UI are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this
project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- A JSON Schema for the data: an index (format version 1) and reports in Bencher Metric
  Format v0.
- `src/lib/contract.ts` loads the index and its reports from a configurable URL. It checks
  each file against the schema and every id the index names, and leaves out reports in a
  format it does not read.
- A first page that lists the benchmarks in the index, by group.
