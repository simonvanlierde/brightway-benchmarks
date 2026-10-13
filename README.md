# brightway-benchmarks

[![python](https://github.com/simonvanlierde/brightway-benchmarks/actions/workflows/python.yml/badge.svg)](https://github.com/simonvanlierde/brightway-benchmarks/actions/workflows/python.yml)
[![license](https://img.shields.io/badge/license-BSD--3--Clause-blue.svg)](LICENSE)

[asv](https://asv.readthedocs.io) benchmarks for the Brightway LCA stack. They run over
released versions, on seeded synthetic systems from `src/bwbench/synth.py`, and use no licensed
data. Each case checks its scores against a float64 reference, so a wrong answer
shows up next to a fast one.

## What is measured

`asv/` holds one asv config per package. Each config installs the releases listed in
`asv/<package>.hashes` from upstream git.

| Package | Benchmarks | Check |
| --- | --- | --- |
| bw2calc | First score, a second demand, `MultiLCA` and `FastScoresOnlyMultiLCA` over 1 to 30 demands, Monte Carlo | Every score against the reference |
| bw2data | `Database.write` | The written database's score, at each size |
| bw_processing | `groups` (#113), `add_entries` (#111) | Group count; none for `add_entries` |
| matrix_utils | `MappedMatrix` build (#48) | Entry count and diagonal |
| bw_graph_tools | Traversal at `max_calc` 2 and 100 (#55) | The starting score |
| bw_timex | `TimexLCA.lci()` (#244) | Static score equals the plain LCA score |

bw2calc picks its solver at import. The base environment gets SuperLU. The other
environments add UMFPACK and, on x86_64, PyPardiso. `BWBENCH_SOLVERS=umfpack` leaves out
the PyPardiso environment. matrix_utils runs against bw_processing 1.6 and the #113 head.

Each config pins numpy, scipy, asv_runner and the Brightway packages around its subject.
Installs only take releases from before 2026-10-06. Each run records what it installed
next to its results.

## Running it

Brightway's code only runs in a throwaway container. With plain Docker, the container sees
the repo read-only, and only `.asv/`, `results/`, `site/` and `asv/` are writable.

```sh
just smoke                       # latest release of each package, smoke size; not results
just bench bw2calc               # every release in asv/bw2calc.hashes
just bench bw2data "4.7^!" -e    # one commit; extra arguments go to asv run
just site                        # history site in site/
```

`BWBENCH_SIZES` and the other `knob(...)` variables in the benchmark files set the sizes.
Smoke results go to `.asv/smoke/`, never to the site. CI runs the smoke pass weekly.

### On the devbox

When `oss-bench` is on the PATH, `box.sh` runs through it. Each run gets a pinned CPU slot,
and its results land under `<host>-<slot>`. oss-bench mounts the whole repo read-write.

```sh
BWBENCH_SIZES=ecoinvent just bench bw2calc
```

At `ecoinvent` size, the generator's random structure needs about 3 GB per SuperLU
factorization. Timings at that size and above are provisional.

### Add a package

1. Copy an `asv/*.json` config and change the project, repo and folders.
2. List its tags or full commit SHAs in `asv/<package>.hashes`.
3. Copy a `benchmarks/bench_*/` folder, keep `__init__.py`, and check scores with `bwbench.check`.
4. Run `just smoke`.

## Development

```sh
uv sync
just check    # lint, types, tests; runs no Brightway code
```

## License

See [LICENSE](LICENSE).
