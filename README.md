# brightway-benchmarks

[![python](https://github.com/simonvanlierde/brightway-benchmarks/actions/workflows/python.yml/badge.svg)](https://github.com/simonvanlierde/brightway-benchmarks/actions/workflows/python.yml)
[![license](https://img.shields.io/badge/license-BSD--3--Clause-blue.svg)](LICENSE)

Benchmarks for the Brightway LCA stack, run over released versions on seeded synthetic
systems. Each timing sits next to a check that the answer is still right.

No licensed data is used: every system comes from `src/bwbench/synth.py`, and the same
seed gives the same system on any machine.

## What is measured

One [asv](https://asv.readthedocs.io) configuration per package, in `asv/`. Each one
installs the releases listed in `asv/<package>.hashes` straight from the upstream
repository.

| Package | Benchmarks | Check beside the timing |
| --- | --- | --- |
| bw2calc | `LCA`, `IterativeLCA` and `JacobiGMRESLCA` first score; a new demand on a factorized system; `MultiLCA` and `FastScoresOnlyMultiLCA` (forward, and adjoint where PR #165's `direction` exists) over 1 to 30 demands; Monte Carlo draws | Score against a SuperLU float64 reference: 1e-9 for direct solvers, 1e-6 for iterative ones. Monte Carlo draws are checked against SuperLU on that draw's matrix. `track_relative_error` records the error per release |
| bw2data | `Database.write` | A written database must give the reference score (1e-6). `track_score_error` records the error |
| bw_processing | `Datapackage.groups` against the group count (#113); `add_entries` against the `dict(vars(entry))` path (#111) | The group count |
| matrix_utils | `MappedMatrix` build against the group count (#48) | The matrix sum |
| bw_graph_tools | Traversal with `max_calc` 2 and 100 (the small case #55 slowed down) | The LCA score it starts from |
| bw_timex | `TimexLCA.lci()` against timeline length (#244) | Both backgrounds are the same system, so the time-explicit static score must equal the plain LCA score (1e-9) |

The solver is part of the bw2calc environment: bw2calc picks PyPardiso, then UMFPACK, then
SuperLU at import. The base environment uses SuperLU. `BWBENCH_SOLVERS` adds
`umfpack` and, on x86_64, `pypardiso`.

The bw2data history includes the commits of #268 (`106d627`, raw SQLite `executemany`)
and #270 (`646849c`, which put peewee's `insert_many` back). Release 4.7 contains both, so
it ships without #268's change, although its changelog lists #268.

`scripts/registry_vs_sqlite.py` compares a bw2data SQLite project with the Parquet
registry proposed in bw2data #290, using sentier-brightway's implementation. It reports
write time, bytes on disk, time to the first score in a fresh process, and the score.

## Running it

Brightway's code runs only in a throwaway `tmp-bwbench-*` container that sees only this
repository (`scripts/box.sh`, image from `docker/Dockerfile`). On the Mac the container
is capped at 2 GB and 2 CPUs; set `BWBENCH_MEM` and `BWBENCH_CPUS` to change that. BLAS
threads are pinned to `BWBENCH_THREADS` (default 1).

```sh
just smoke                        # one quick pass per package at its latest release
just bench bw2calc                # every release in asv/bw2calc.hashes
just bench bw2data "4.7^!"        # one commit, as an asv range
just registry-vs-sqlite           # the #290 comparison, smoke size
just site                         # static history site in site/
```

Sizes come from the environment, because asv reads parameters at import:
`BWBENCH_SIZES` (`smoke`, `ecoinvent`, `exiobase`, `regional`), `BWBENCH_MC_SIZES`
(`smoke`, `mc100k`), `BWBENCH_WRITE_SIZES`, `BWBENCH_TIMEX_SIZES`, `BWBENCH_GROUPS`,
`BWBENCH_ENTRIES`, `BWBENCH_STEPS` and `BWBENCH_ITERATIONS`. `BWBENCH_MACHINE` labels the
results: set one name per host and CPU slot.

## What still needs a quiet machine

The Mac runs prove that the harness works. Their numbers are single samples (`--quick`)
at the smoke size, on 2 shared CPUs, and none of them is a result.

- Every real timing: the devbox, one pinned `oss-bench` slot, sizes from `ecoinvent` up.
- The run-to-run noise floor (10 repeats), before any comparison is published.
- PyPardiso, which has no ARM wheels: x86_64 only.
- The release backfill for each package, and the `results/` and `site/` that go public.
- Calibrating the generator: only the product counts in `SIZES` have a source.

## Development

```sh
uv sync
just check       # lint, types and tests for this repo's own code (host-safe)
```

## License

See [LICENSE](LICENSE).
