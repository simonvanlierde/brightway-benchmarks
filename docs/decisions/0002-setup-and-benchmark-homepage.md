# 0002. A tested setup and benchmark evidence on the homepage

- Status: accepted; amended by 0003
- Date: 2026-11-01
- Amends: 0001, audience priority and the site landing page

## Context

The site serves two audiences. Brightway users need a tested starting environment and solver
alternatives. Maintainers need release changes with the measurements and noise behind them.
There are too few practical stack choices to warrant a selection wizard.

The existing compatibility workflow already publishes tested sets, check results and the last
passing environment files. Its smoke calculations, dependency diagnostics and package test
suites establish different things. A passing smoke check does not establish that every package
test passes. Benchmark measurements also use fixed environments distinct from those snapshots.

## Decision

The homepage leads with a tested setup for the selected platform and measured solver
alternatives. A compact section shows both regressions and improvements, linking to the full
release-change view. A dedicated Compatibility tab presents the tested environments and the
selected check's current result, coverage, last passing set and installation files.

- Recommendations describe a verified starting point, with their date and test scope. They do
  not claim the fastest setup for every workflow or machine.
- The exporter writes optional `guidance.json` beside the benchmark index and reports. It
  supplies project-specific labels, setup advice and coverage. The viewer remains data-driven.
- Solver comparisons come from matching benchmark reports on one release and machine. The
  source environment remains inspectable through the benchmark link.
- The viewer becomes the site landing page and keeps its existing `ui/` address. All asv
  subject pages stay at their current paths. The former landing page remains at `asv.html`.
  The two-week parity condition in 0001 still applies before removing the asv pages.

On wide screens, tested setup and solver evidence sit side by side; regressions and
improvements follow below. [DESIGN.md](../../DESIGN.md) describes the look.

## Consequences

The site build needs both benchmark exports and the current compatibility snapshot. Missing
setup evidence leaves benchmark navigation available; it must not produce a successful test
result or an invented recommendation. The full compatibility view retains diagnostic and
failed checks alongside successful ones.

We maintain and test two public entry addresses for the same viewer. Both load the same data
and assets. Existing benchmark query links and the `#works-together` compatibility link remain
usable.
