# Product

## Platform

web

## Users

The homepage helps LCA practitioners choose a tested starting point for their platform. Maintainers investigate release changes and measurement noise on Benchmarks. Contributors and scientific Python readers inspect machine comparisons, solver behaviour, and raw measurements.

## Audience

Each page serves a primary reader. What they come for must sit in the first screen:

- **Setup (`/`)** — *LCA practitioner or student choosing an install.* Comes for a working install command for their OS, Python version, and package manager. First screen: OS-matched install command, check status, and the one-line solver takeaway.
- **Benchmarks (`/?page=explorer`)** — *Brightway maintainer or contributor.* Comes to spot regressions, inspect release histories, and check Python support. First screen: solver comparison, latest release changes (improvements open when few), and Python support; on a benchmark view, the exact call, environment/thread settings, and noise floor.
- **Across machines (`/?page=compare`)** — *Contributor running `bwbench compare` or user checking another OS.* Comes to see whether a solver or option holds across hardware. First screen: ratio key, machine rows, and 95% intervals.
- **Findings (`/findings/`)** — *Practitioner, developer, or SciPy reader.* Comes for concrete results without digging through charts. First screen: visible **Stories** list, package-grouped **Headlines** with version, thread, and matrix caveats, then **Write-ups**.
- **Stories (`/stories/*`)** — *Practitioner or SciPy reader arriving from a link.* Comes for a self-contained answer. First screen: plain-language takeaway, exact scope (threads, matrix, package versions), and copyable commands or model checks.
- **About (`/about/`)** — *Anyone checking methodology or privacy.* First screen: what the benchmarks cover, what a passing setup means, citation, and browser storage policy.

## Product Purpose

Help users choose a tested setup for their platform, then inspect the benchmark evidence behind alternatives and release changes.

## Capabilities and Constraints

The viewer in `ui/` is a static Astro and Svelte app. It reads versioned JSON through one contract adapter. Names, descriptions, groups, environments, machines and links come from the data, so the viewer explains Brightway terms without holding Brightway-specific logic. Change detection runs in the exporter. An optional versioned guidance file supplies platform setups, current check results, last passing install commands per package manager and curated solver comparisons. A shareable URL holds the page, platform, selected check, benchmark, parameters, measure and machine. Each chart has a data table and an SVG download.

Platform choices open the published default directly, without a wizard. If guidance is absent, benchmark histories and release changes remain available. Keep each page’s gzipped HTML, JavaScript and linked CSS within the budgets in `ui/scripts/size.mjs`, one for the viewer (lazy chart chunks included) and one for static pages. Data files are excluded.

Keep experimental commits visible without treating them as releases. Keep machines separate and show failed or missing reports honestly. Preserve the independent correctness checks behind every timing.

## Evidence on Hand

`ui/test/fixtures/real/` contains published benchmark results for browser tests. `docs/decisions/0001-own-benchmark-ui.md` records the static viewer and open data contract. `docs/decisions/0002-setup-and-benchmark-homepage.md` and `0003-two-pages-and-no-asv-pages.md` record the Setup and Benchmarks pages. `benchmarks/findings.toml` holds the curated findings. Scientific claims come from this evidence, never illustrative values.

## Product Principles

- Distinguish installation coverage from performance evidence, and current failures from older passing sets.
- Put changes and their uncertainty together.
- Keep comparisons reproducible and inspectable.
- Make the current selection clear and shareable.
- Keep the viewer independent of its benchmark harness.

## Accessibility & Inclusion

WCAG 2.2 AA, full keyboard use, tables behind charts, light and dark themes, and phone widths are required.
