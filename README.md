# brightway-benchmarks

[![python](https://github.com/simonvanlierde/brightway-benchmarks/actions/workflows/python.yml/badge.svg)](https://github.com/simonvanlierde/brightway-benchmarks/actions/workflows/python.yml)
[![license](https://img.shields.io/badge/license-BSD--3--Clause-blue.svg)](LICENSE)

How fast is [Brightway](https://docs.brightway.dev), and does it still give the right answer?
This repository times the calculations an LCA practitioner runs every day, such as an LCI and
LCIA, many functional units at once, or Monte Carlo, across Brightway's released versions.
It also checks every result against an independent reference score. A release that makes a
calculation slower, or quietly changes a score, shows up here.

No licensed data is used. The benchmarks run on synthetic databases that copy the structure
of ecoinvent, so anyone can rerun them and the results can be published.

## What is measured

| Package | What is timed, in LCA terms |
| --- | --- |
| bw2calc | One score (build the matrices, solve, characterize); a second functional unit on a system already solved; many functional units against three impact categories; Monte Carlo draws. Each with the direct solver (PyPardiso, UMFPACK or SuperLU) and bw2calc's iterative solvers |
| bw2data | Writing a database, up to the size of ecoinvent |
| bw_processing, matrix_utils | Building datapackages and matrices from many resource groups |
| bw_graph_tools | Supply-chain graph traversal, small and large |
| bw_timex | The time-explicit LCI as the timeline grows |

Every score is checked next to its timing, against a reference that uses no Brightway code
at all, so a fast but wrong release fails instead of looking good. Only the bw_processing
cases that build datapackages from entries have nothing to check.

## The synthetic databases

A database is generated from a seed, so the same settings give the same matrices on every
machine. Its shape comes from a profile:

- `ecoinvent` has 26,533 products, like ecoinvent 3.12 cut-off. It reproduces the measured
  structure of that release: how many inputs each process has and how many consumers each
  product has, the one large loop that holds 64% of the products, waste treatments with
  negative inputs, per-product units spanning many orders of magnitude, and a spectral
  radius of 0.78. Only aggregate statistics of ecoinvent went into it, never a dataset.
  They are in [`src/bwbench/profiles/`](src/bwbench/profiles).
- `smoke` is the same structure at 200 products, for quick checks.
- `mc100k` and `regional` scale it to 100,000 and 250,000 products, the sizes of a large
  Monte Carlo study and a regionalised database.
- `exiobase` and `stress-random` use a random structure, a worst case for the solvers.

One known difference: factorizing the `ecoinvent` profile costs more than factorizing the
real ecoinvent (LU fill of 323 against 175 with SuperLU's default ordering). The real
database's suppliers share more of their consumers. [TODO.md](TODO.md) tracks the work on
it.

## Running it

You need Docker and [just](https://just.systems). Brightway's code only runs inside a
throwaway container, never on your machine.

```sh
just smoke                       # each package's latest release, small database: a quick check
just bench bw2calc               # every bw2calc release listed in asv/bw2calc.hashes
just bench bw2data "4.7^!" -e    # one release; extra arguments go to asv
just site                        # build the history pages in site/
```

`BWBENCH_SIZES=ecoinvent` (or `smoke,ecoinvent`) picks the databases. The results are not
published yet: the run-to-run noise still has to be measured first.

## How the results stay reproducible

- Each package is benchmarked with [asv](https://asv.readthedocs.io), against pinned
  versions of numpy, scipy and the other Brightway packages, and only releases from before
  2026-10-06.
- The solvers run on one thread, so a timing does not depend on how many cores were free.
- Each run records exactly what was installed (a `pylock.toml` lock file per environment)
  and an RO-Crate that names the code and settings that produced it.

## For developers

`uv sync`, then `just check` runs lint, types and tests. These run no Brightway code.

- Benchmarks: [`benchmarks/`](benchmarks), configs and releases: [`asv/`](asv)
- Security: [SECURITY.md](.github/SECURITY.md)
- License: [LICENSE](LICENSE)
