# Benchmark UI

A static site that shows benchmark results. It reads two kinds of JSON file, which
[schema/](schema/) describes:

- `index.json`: the benchmarks, their parameters, environments, machines, commits, releases and
  reports ([index.schema.json](schema/index.schema.json)).
- one report per commit and machine, in [Bencher Metric Format](https://bencher.dev/docs/reference/bencher-metric-format/)
  v0 ([report.schema.json](schema/report.schema.json)).

The site has no server and knows nothing about the project it shows: every name, group and link
comes from the data. [src/lib/contract.ts](src/lib/contract.ts) is the only module that reads
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
clone that has asv's mirrors in `.asv/` (they give the release names) into that folder.

The site reads `index.json` from `PUBLIC_DATA_URL`, an absolute URL or a path relative to the
page, `data/` by default. Set it at build time:

```sh
PUBLIC_DATA_URL=https://example.org/bench-data/ pnpm build
```

The data folder must hold `index.json`, with each report at the `path` the index gives.

## What it shows

The start page lists what moved beyond its noise in each group's newest release. Each
benchmark has a page: its history over the group's commits, one line per environment, for the
parameters, measure and machine picked above the chart. These live in the URL (`bench`, one `p`
per parameter axis, `measure`, `machine`), so a link opens the same view. Below the chart are the
changes the index lists for those lines, and a table with every value.

The chart takes focus: the arrow keys, Home and End step through the releases, and the same text
as the pointer's tip is read out.

## The data

Reports have Bencher Metric Format's shape, but their keys are case ids ending in a hash, so
they are not for upload to Bencher. A case's id includes its environment's name, which holds
the pinned versions, so a pin bump starts a new series.

An environment's optional `label` is the name to show, such as the solver it runs; the full name
stays under the data table. A measure's optional `bounds` says what a metric's lower and upper
values are, and the chart's caption repeats it.

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
