# Two pages, dated install sets, and no asv pages

- Status: accepted
- Date: 2026-11-01
- Amends: [own-benchmark-ui.md](own-benchmark-ui.md), the asv parity condition; [setup-and-benchmark-homepage.md](setup-and-benchmark-homepage.md), the four tabs and `asv.html`

## Context

The viewer had four tabs: Home, Compatibility, Release changes and Benchmark explorer. Home and
Compatibility showed the same checks twice, and Release changes and the explorer showed the same
benchmarks twice. The explorer, which the site was built for, sat last. On a laptop, Home left
half the screen empty when the solver comparison was missing.

Install sets lived only as workflow artifacts, which GitHub deletes after 90 days, and the page
offered `requirements.txt` with one `uv pip` command. Many Brightway users install with conda.

The asv pages were kept until the viewer reached parity (own-benchmark-ui.md). They were reached only from the
footer and from old links in `docs/findings.md`.

## Decision

The masthead has two pages and a search box. **Setup** puts install first: a platform, a command
per package manager (uv, pip, conda, pixi), the check results, then every check as a grid whose
cells select the set above. Beside it sit the solver comparison, curated findings and the latest
changes. **Benchmarks** opens on the findings and the release changes, each with a small history
line, and a catalogue rail; a benchmark's view explains each parameter under its control on desktop and in a disclosure on phones, and links
values, solvers and its source.

- Install commands name a dated folder that never changes; a second link copies the undated one,
  which follows the newest passing set. A `compat` branch keeps every set, so the dated folders
  outlive the artifacts.
- Findings come from `benchmarks/findings.toml`, so each claim on the page is written once, by
  hand, and links the chart that shows it. The export stops when one names a missing benchmark.
- Each page's main content fits a 1440 by 900 screen.
- The site stops publishing asv's pages. Their addresses redirect into the viewer. This drops
  the two-week wait in own-benchmark-ui.md: the viewer already shows every history asv did, and nothing else links
  to those pages.

## Consequences

Old links keep working: `?page=compatibility` and `#works-together` open Setup at the grid,
`?page=changes` opens Benchmarks, and `<subject>/#<benchmark>` opens that history. The asv
results stay on the `results` branch, so the pages can be built again with `asv publish` if
needed.

The site build reads the `compat` branch, so the compat workflow must run on `main` before the
first deploy that needs it. The findings need care when results change: the export catches a
missing benchmark, not a claim the numbers no longer support.
