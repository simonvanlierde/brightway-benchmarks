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
pnpm check      # lint, type checks and tests
```

The site reads `index.json` from `PUBLIC_DATA_URL`, an absolute URL or a path relative to the
page, `data/` by default. Set it at build time:

```sh
PUBLIC_DATA_URL=https://example.org/bench-data/ pnpm build
```

The data folder must hold `index.json`, with each report at the `path` the index gives.

## Change the schema

Edit the files in `schema/`, then run `pnpm types` to regenerate the TypeScript types in
`src/lib/*.gen.ts`. Raise `format_version` (and `FORMAT_VERSION` in `contract.ts`) when an older
reader would misread the new files. Adding an optional field needs no new version: readers
ignore fields they do not know.
