# brightway-benchmarks

[![python](https://github.com/simonvanlierde/brightway-benchmarks/actions/workflows/python.yml/badge.svg)](https://github.com/simonvanlierde/brightway-benchmarks/actions/workflows/python.yml)
[![license](https://img.shields.io/badge/license-BSD--3--Clause-blue.svg)](LICENSE)

[asv](https://asv.readthedocs.io) benchmarks for the Brightway LCA stack (bw2calc, bw2data,
bw_processing, matrix_utils, bw_graph_tools, bw_timex), run over released versions on seeded
synthetic systems from `src/bwbench/synth.py`. No licensed data is used.

Each case checks its scores against a float64 reference, so a wrong answer shows up next to
a fast one.

## Quick start

Brightway's code only runs in a throwaway container.

```sh
just smoke                       # latest release of each package, smoke size; not results
just bench bw2calc               # every release in asv/bw2calc.hashes
just bench bw2data "4.7^!" -e    # one commit; extra arguments go to asv run
just site                        # history site in site/
```

Test conditions: each config in `asv/` pins numpy, scipy, asv_runner and the Brightway
packages around its subject, installs only releases from before 2026-10-06, and records
what it installed next to its results.
`BWBENCH_SIZES` picks the profiles. `ecoinvent` copies the structure of ecoinvent 3.12
cut-off, measured in `src/bwbench/profiles/`. `smoke` is a 200-product version of it, and
`mc100k` and `regional` scale it to 100k and 250k products. `exiobase` and `stress-random`
keep the earlier random structure, whose LU factors fill several times more than a real
database's.

For development: `uv sync`, then `just check` (lint, types, tests; runs no Brightway code).

## Links

- Benchmarks: [`benchmarks/`](benchmarks), configs and releases: [`asv/`](asv)
- Security: [SECURITY.md](.github/SECURITY.md)
- License: [LICENSE](LICENSE)
