# 0007. Comparisons across machines, under Benchmarks

- Status: accepted
- Date: 2026-11-14
- Amends: 0006, what Benchmarks carries

## Context

The ratio job times one choice against its usual alternative (a solver, an install route, a
Python version, a release) on several machines in the same run, and gives a ratio with a 95%
interval per machine. Hosted runs are attested; contributed runs are not verified. A practitioner
wants to know whether a difference holds on a machine like theirs, so the page needs every
machine's row, not one pooled number. The masthead has three items (0005), and 0006 put the
evidence on Benchmarks and Findings.

We weighed three places for it:

- A section on the Benchmarks overview. It already holds the solver comparison, the release
  changes and two Python tables, and five more tables would push them down.
- A fourth masthead item. It splits the navigation 0003 simplified, for a view that is evidence
  like the rest of Benchmarks.
- A view of its own under Benchmarks, as a benchmark's history is.

## Decision

The comparisons are a viewer view at `?page=compare`, "Across machines", under Benchmarks: the
masthead marks Benchmarks and the catalogue stays beside it. The Benchmarks intro and Setup's
"From the benchmarks" list link it while ratios are published.

- One table per comparison, one row group per candidate and one row per machine: its ratio, 95%
  interval, the interval drawn on a log scale around 1, and its source (reference, hosted with a
  link to its run, or contributed, unverified).
- Each candidate's summary is a range over the machines whose interval leaves out 1, when they
  agree in direction, and "Differs between machines" when they do not, followed by how many
  machines show no clear difference. Never a pooled estimate.
- Only reference and hosted machines count towards the summary. Contributed rows are still shown,
  marked unverified. When no reference or hosted machine measured a candidate, the summary covers
  the contributed machines and says so.
- `scripts/export_ratios.py` writes `ratios.json` beside `index.json`, summary included, so the
  viewer computes none. The file is optional: without it the view says none are published.

## Consequences

The site build reads the `ratios` branch (`just site`) and `ratios/contributed/` on main. A
file's tier comes from its folder, so a contributed file cannot claim to be hosted. The ratios
time a small case, so a ratio here says whether a difference holds across machines, not how
large it is on a full database; each table names its case and size.
