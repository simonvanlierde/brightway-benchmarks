# Product

## Platform

web

## Users

The homepage helps users choose a tested starting point for their platform. Maintainers investigate release changes and measurement noise in dedicated release-change and benchmark-explorer views. Readers of the study can inspect the same underlying measurements.

## Product Purpose

Help users choose a tested setup for their platform, then inspect the benchmark evidence behind alternatives and release changes.

## Capabilities and Constraints

The viewer in `ui/` is a static Astro and Svelte app. It reads versioned JSON through one contract adapter. Names, descriptions, groups, environments, machines and links come from the data, so the viewer explains Brightway terms without holding Brightway-specific logic. Change detection runs in the exporter. An optional versioned guidance file supplies platform setups, current check results, last passing installation files and curated solver comparisons. A shareable URL holds the primary view, platform, compatibility filters, selected check, benchmark, parameters, measure and machine. Each chart has a data table and an SVG download.

Platform choices open the published default directly, without a wizard. If guidance is absent, benchmark histories and release changes remain available. Keep the gzip total of built HTML, JavaScript and CSS within the budget in `ui/scripts/size.mjs`; data files are excluded.

Keep experimental commits visible without treating them as releases. Keep machines separate and show failed or missing reports honestly. Preserve the independent correctness checks behind every timing.

## Evidence on Hand

`ui/test/fixtures/real/` contains published benchmark results for browser tests. `docs/decisions/0001-own-benchmark-ui.md` records the static viewer and open data contract. `docs/decisions/0002-setup-and-benchmark-homepage.md` records the setup and benchmark views. Scientific claims come from this evidence, never illustrative values.

## Product Principles

- Distinguish installation coverage from performance evidence, and current failures from older passing sets.
- Put changes and their uncertainty together.
- Keep comparisons reproducible and inspectable.
- Make the current selection clear and shareable.
- Keep the viewer independent of its benchmark harness.

## Accessibility & Inclusion

WCAG 2.2 AA, full keyboard use, tables behind charts, light and dark themes, and phone widths are required.
