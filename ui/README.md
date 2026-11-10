# Benchmark UI

A static site that shows Brightway benchmark results. It reads two kinds of JSON file, which
[schema/](schema/) describes:

- `index.json`: the benchmarks, their parameters, environments, machines, commits, releases and
  reports ([index.schema.json](schema/index.schema.json)).
- optional `guidance.json`: tested setups, compatibility coverage and curated comparisons ([guidance.schema.json](schema/guidance.schema.json)).
- one report per commit and machine, in [Bencher Metric Format](https://bencher.dev/docs/reference/bencher-metric-format/)
  v0 ([report.schema.json](schema/report.schema.json)).

The viewer has no server. Benchmark names, groups and links come from the data; the landing
page and About page explain this Brightway project. [src/lib/contract.ts](src/lib/contract.ts) is the only module that reads
the files, and it checks each one against the schema.

## Use

Node 24 or later, and pnpm:

```sh
pnpm install
pnpm dev        # a local server with live reload
pnpm build      # the static site, in dist/
pnpm check
pnpm test
pnpm size       # after a build: what a page loads, gzipped, against the budget
pnpm e2e        # after a build: browser tests, with axe and screenshots (SHOTS=folder)
```

The browser tests need Playwright's Chromium once: `pnpm exec playwright install chromium`.
They serve `dist/` with [test/fixtures/real/](test/fixtures/real/) as its data: a copy of
`just ui-data` run on the public `results` branch. To refresh it, run `just ui-data` from a
clone that has asv's mirrors in `.asv/` (they give the release names) into that folder. Its
`guidance.json` comes from [test/fixtures/compat/status.json](test/fixtures/compat/status.json):
`python3 scripts/export_guidance.py ui/test/fixtures/compat/status.json ui/test/fixtures/real`, and a
pytest fails when the two drift apart.

To look at a UI change, `just ui-serve` (port 4400 by default) builds the viewer and serves it
with that same data. CI's `ui` job also keeps the browser tests' screenshots as the
`ui-screenshots` artifact for 14 days: `gh run download <run id> -n ui-screenshots`.

The site reads `index.json` from `PUBLIC_DATA_URL`, an absolute URL or a path relative to the
page, `data/` by default. Set it at build time:

```sh
PUBLIC_DATA_URL=https://example.org/bench-data/ pnpm build
```

The data folder must hold `index.json`, with each report at the `path` the index gives, and may
hold `guidance.json`.

## What it shows

Setup starts with labelled operating-system, Python-version and package-manager selectors above the install command. There is one install command per package manager (uv, pip, conda or pixi), chosen with a package-manager select (the choice is remembered in this browser). A command names a dated set that never changes; "Copy latest" copies the one that follows the newest passing set. Selecting a check keeps that check’s install set; a failed check without a passing set says so. Changing package manager selects a matching check for that Python version and updates the URL; it never substitutes another Python version. With no explicit check, the page chooses a matching check on the platform. The command's source check, any matching upstream-suite result, and coverage caveats appear before Copy. An optional “Starting a new project?” section gives uv users a complete project-creation command sequence. Below, every check appears in a comparison grid: select a cell to install its set. A smoke pass and an upstream test-suite pass are separate claims. If the current check fails, the earlier passing files keep their date and run link.

Beside the setup sit the solver comparison, the curated findings from `benchmarks/findings.toml`, and the latest release changes. The solver timings use the benchmark stack named with the comparison, which may differ from the setup's compatibility snapshot.

Benchmarks opens on the findings and on what moved beyond its noise in each group's newest release, each change with a small history line. Filter by package or change direction; counts follow the selected package. The catalogue rail and the masthead search (Enter opens the first match) lead to each benchmark's history, one line per environment. Each parameter's meaning sits under its control on desktop and under “Parameter details” on phones. Values, solvers and the benchmark's source link to their documentation. Original identifiers remain in link titles and the detail view.

The page, platform, selected check and benchmark settings live in the URL. Existing `?bench=` links still open the same history, `?page=compatibility` and `#works-together` open Setup at the grid, `?page=changes` opens Benchmarks, and the old asv addresses redirect to the matching history. Each chart has a data table and an SVG download; arrow keys, Home and End read its releases.

On phones, change tables reflow into labelled rows and checks appear as a list for the selected platform. Desktop keeps the comparison grid, with a pinned platform column and a hint when it needs sideways scrolling. Measurement tables scroll inside their own focusable region. Selecting a check moves to the install command.

If optional guidance is missing or cannot be read, the viewer explains the gap and keeps benchmark histories available. It never fills missing setups or measurements with example values.

The masthead holds navigation, search and a sun/moon theme toggle. The theme follows the system until you choose one, then remembers your choice. The latest published check date sits beside Checks; GitHub and the exact release tag or commit used to build the site sit in the footer. The static About page explains the measurements, data sources, citation and privacy. Both pages include search and sharing metadata and appear in the sitemap. They also embed `SoftwareSourceCode` JSON-LD, built from [codemeta.json](../codemeta.json) so the repository, licence and authors share the project’s maintained metadata. Sharing cards use an absolute image URL with dimensions and alternative text. Regenerate the committed icons and preview image with `pnpm assets`; the preview describes the evidence without claiming a current check result. Deployment fails if a required icon or preview image is missing. The size check measures each page separately: the viewer has a 182 KB gzip budget including lazy chart chunks, and static pages have a 20 KB budget.

## The data

Reports have Bencher Metric Format's shape, but their keys are case ids ending in a hash, so
they are not for upload to Bencher. A case's id includes its environment's name, which holds
the pinned versions, so a pin bump starts a new series.

An environment's optional `label` is the name to show, such as the solver it runs; the full name
stays under the data table. A measure's optional `bounds` says what a metric's lower and upper
values are, and the chart's caption repeats it. Its optional `noise` is the exporter's rule for
how far a value may move as noise, and the chart draws it as the band around each line.

The index's optional `changes` are worked out before the data is written, not in the browser:
the UI only draws them. This repository's exporter finds them with a noise threshold between
releases and with Apache Otava ([scripts/export_ui.py](../scripts/export_ui.py)).

## Change the schema

Edit `schema/`, then run `pnpm types` to regenerate `src/lib/*.gen.ts`. The `format_version`
description in [index.schema.json](schema/index.schema.json) says when the version goes up;
raise `FORMAT_VERSION` in `contract.ts` with it.

## Known gaps

- No mark of which dependency stack a value ran on, so a chart cannot show where it moved.
- No series key that survives a pin bump.
