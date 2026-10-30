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
```

The site reads `index.json` from `PUBLIC_DATA_URL`, an absolute URL or a path relative to the
page, `data/` by default. Set it at build time:

```sh
PUBLIC_DATA_URL=https://example.org/bench-data/ pnpm build
```

The data folder must hold `index.json`, with each report at the `path` the index gives.

## The data

Reports have Bencher Metric Format's shape, but their keys are case ids ending in a hash, so
they are not for upload to Bencher. A case's id includes its environment's name, which holds
the pinned versions, so a pin bump starts a new series.

## Change the schema

Edit `schema/`, then run `pnpm types` to regenerate `src/lib/*.gen.ts`. The `format_version`
description in [index.schema.json](schema/index.schema.json) says when the version goes up;
raise `FORMAT_VERSION` in `contract.ts` with it.

## Known gaps

- No mark of which dependency stack a value ran on, so a chart cannot show where it moved.
- No series key that survives a pin bump.
