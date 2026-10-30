# 0001. Our own benchmark UI, on an open data contract

- Status: accepted
- Date: 2026-10-30

## Context

asv's published pages are hard to read, and they show one benchmark at a time with no view of
what changed between releases. We weighed three ways out:

- Bencher, self-hosted. Its plots are good, but it is open-core: closing sign-up on a
  self-hosted server and turning off its usage reports are reserved for the paid version
  (bencherdev/bencher#640 and #641).
- Another tracker. Conbench has had no release since March 2024, and github-action-benchmark
  draws one line per benchmark, with no parameters, environments or releases.
- A UI of our own, reading files that this repo publishes.

Other projects, such as pymrio, could use the same UI later, so it should be easy to move into
its own repository.

## Decision

We build a static UI that reads versioned JSON files: each report's metrics in Bencher Metric
Format, an open format that many benchmark harnesses can already produce, plus our own index of
benchmarks, parameters, environments, machines, releases and change points, described by a JSON
Schema. The UI has no server and no Brightway knowledge: names, groups and links come from the
data.

- It lives in `ui/` as its own pnpm package that imports nothing from outside `ui/`, so it can
  move into its own repository with its history.
- It is built with Astro and Svelte. The chart library is chosen by building the same chart in
  LayerChart and in Observable Plot.
- Changes are found in the night job, not in the browser: a change between releases counts
  only when it is larger than that case's measured noise, and Apache Otava marks change points
  along each series. Not built yet: noise, change points and the night job.
- It serves maintainers first (what changed, and is it noise), then users (what to install),
  then readers of the study.
- It runs beside asv's pages until it shows everything they show, plus two weeks of night runs
  without a fix. Then asv's pages go and their links redirect.

## Consequences

- One exporter turns asv results into the contract, and the schema tests keep it and the UI in
  step. Another harness needs only its own exporter.
- The format sits behind one reading module in the UI, so moving to our own format or another
  standard later changes that module only.
- A later upload service would write the same files, so nothing here may assume a server.
- After `ui/` moves out, this repository keeps a pinned copy of the schema and checks the
  `format_version` of the files it writes against it.
- We now maintain a frontend: accessibility (WCAG 2.2 AA, a table behind every chart, keyboard
  use), light and dark themes, phone widths, browser tests and a size budget
  ([ROADMAP.md](../../ROADMAP.md)).
