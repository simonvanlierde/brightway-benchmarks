# Running the benchmarks

You need Docker and [just](https://just.systems); `just results-commit` also needs rsync and git
2.42 or later. Brightway's code runs only in a throwaway container, the box
([assurance case](assurance-case.md)). `just` lists every recipe.

## Benchmarks

```sh
just smoke                       # each package's oldest and latest release, small database
just bench bw2calc               # every bw2calc release listed in asv/bw2calc.hashes
just bench bw2data "4.7^!" -e    # one release; extra arguments go to asv
just site                        # build the history pages in site/
just release-changes bw2calc     # what moved in bw2calc's latest release, as a Markdown table
just ui-data site/data           # results/ as the data the UI in ui/ reads
just results-commit              # keep results/ on the local results branch, for publishing
just solver-lci klu ecoinvent    # bw2calc 3.1.0's own lci() with one solver, KLU here
just codspeed bw2calc pypardiso  # one suite under CodSpeed's CPU simulation (instruction counts)
```

Cases run on the 200-product `smoke` database unless `BWBENCH_SIZES` names others, as in
`BWBENCH_SIZES=ecoinvent just bench bw2calc`. A full-size bw2calc run takes about 24 minutes,
or 6 with `BWBENCH_SOLVERS=pypardiso`, and `BWBENCH_ROUNDS=1` halves it. `just bench` skips what
already succeeded, so a stopped run resumes.

The `codspeed` workflow runs `benchmarks/codspeed` on each pull request and push to `main`
([CodSpeed](https://app.codspeed.io/simonvanlierde/brightway-benchmarks)).
`just results-commit` refuses results that name this host or a name in
`BWBENCH_PRIVATE_NAMES`.

### Experimental solvers

Two bw2calc environments run only when named, as in `BWBENCH_SOLVERS=klu,umfpack-T`: `klu`
(KLU through pyklu, x86_64 only) and `umfpack-T` (scikit-umfpack factorizing Aᵀ). bw2calc
cannot pick either, so [`src/bwbench/solvers.py`](../src/bwbench/solvers.py) patches them in.
A case fails if bw2calc never reached the patch.

### bw2calc on conda-forge's builds

`just bench bw2calc-conda` runs the bw2calc suite for 2.4.0 and 3.1.0 on conda-forge's NumPy,
SciPy, PyPardiso and scikit-umfpack (on OpenBLAS and on MKL's BLAS), at the fixed stack's
versions ([`asv/bw2calc-conda.json`](../asv/bw2calc-conda.json)). Each run writes the conda
build strings, the BLAS among them, to a `versions-*.txt` file.

### Measure the noise

`just noise SUBJECT` runs the latest release of SUBJECT 10 times and prints each case's spread
([method.md](method.md#the-noise-floor)). Each sample's CPU time, wall time and context
switches go to `rounds.jsonl`; `scripts/noise_summary.py` reads them.

## Memory

The box has 2 GB and no swap by default. A job over the limit is killed: under asv as a failed
benchmark, otherwise with exit 137. Set `BWBENCH_MEM` to give it more.

## Add a release

1. Add it to `asv/<package>.hashes`.
2. Move the cutoff in `scripts/in-box.sh`.
3. Run `just stack <package>` to resolve the new fixed set of dependencies.
4. Run `just stack-check <package>`, and drop the releases that no longer run on it.

[method.md](method.md#how-the-results-stay-reproducible) says why the set is fixed.

## Compat

`just compat PYTHON [COLUMN]`, as in `just compat 3.12 floors`, asks whether the newest
releases work together. It installs the latest brightway25, bw_graph_tools and bw_timex into a
fresh environment and runs every case once at the `smoke` size, untimed.

- `latest` (default): the newest release of everything.
- `floors`: Brightway's direct dependencies at the oldest version Brightway allows that has a
  wheel. A bound already found too low is raised to the oldest release that works, as listed in
  `scripts/compat.sh`.
- `pre`: like `latest`, with pre-releases.
- `conda-forge`: the same set from conda-forge with pixi, without the bw_graph_tools and
  bw_timex cases. Linux only.
- `suites`: like `latest`, but runs the test suites of bw2data, bw2calc, bw2io, bw_processing,
  matrix_utils, bw_graph_tools and bw_timex, from each package's GitHub tag. Linux only.

bw_timex pulls in PyPardiso on Linux x86_64, so there bw2calc solves with PyPardiso.

Each run writes to `.asv/compat/PYTHON-COLUMN/`: `requirements.txt`, and `pylock.toml` with
each wheel's hash for that job's operating system. `conda-forge` also writes `pixi.toml` and
`pixi.lock`. `suites` writes `suites.txt` with each package's result and `suites/PACKAGE.log`.

### The nightly runs

The `compat` workflow runs `latest` on Linux with Python 3.12, 3.13 and 3.14, and on macOS and
Windows with 3.12. `pre` runs on Linux with 3.14, the other columns with 3.12. Only `latest`
turns the run red, so check the other jobs yourself. On macOS and
Windows the job runs on the runner, not the box. On macOS the PyPardiso and UMFPACK cases skip,
since neither installs from PyPI there.

### Install a set that works

The site's [works together today](https://simonvanlierde.com/brightway-benchmarks/#works-together)
table shows the latest nightly result per job and the last set that passed. Download its
`requirements.txt` and use it as constraints:

```sh
uv pip install brightway25 -c requirements.txt
```

For the `conda-forge` row, download `pixi.toml` and `pixi.lock` into one folder and run
`pixi install --frozen` there. A set is kept for 90 days, as long as GitHub keeps the
workflow's artifacts.

## Environment variables

`scripts/box.sh` passes every `BWBENCH_*` variable into the box.

| Variable | Default | What it sets |
| --- | --- | --- |
| `BWBENCH_SIZES` | `smoke` | Database sizes: `smoke`, `ecoinvent`, `mc100k`, `regional`, `exiobase`, `stress-random`, `useeio` (real data, downloaded once; [method.md](method.md#the-real-database)) |
| `BWBENCH_MC_SIZES` | `smoke` | Sizes for bw2calc's Monte Carlo |
| `BWBENCH_WRITE_SIZES` | `smoke` | Sizes for bw2data's write |
| `BWBENCH_TIMEX_SIZES` | `smoke` | Sizes for bw_timex |
| `BWBENCH_ITERATIONS` | `10` | Monte Carlo draws per case |
| `BWBENCH_GROUPS` | `100,1000` | Resource groups |
| `BWBENCH_ENTRIES` | `10000,100000` | bw_processing entries |
| `BWBENCH_STEPS` | `5,20` | bw_timex time steps |
| `BWBENCH_SOLVERS` | `superlu,pypardiso,umfpack` (no `pypardiso` off x86_64) | Solver environments |
| `BWBENCH_ROUNDS` | `2` | asv rounds per case |
| `BWBENCH_CPUS` | `2` | CPUs for the box |
| `BWBENCH_MEM` | `2g`; `6g` compat, `12g` solver-lci | Box memory, no swap |
| `BWBENCH_THREADS` | `1` | BLAS and OpenMP threads |
| `BWBENCH_MACHINE` | `box-<slot>` or `box` | asv machine name; resume needs the same one |
| `BWBENCH_PRIVATE_NAMES` | empty | Names `just results-commit` refuses |
| `BWBENCH_ROUNDLOG` | unset | Per-sample log; `just noise` sets it |
| `BWBENCH_STRICT` | `1` in compat | Fail, not skip, a case the installed releases cannot run; a case for another solver still skips |
| `BWBENCH_TARGET` | `box` | Dockerfile stage; recipes set it |
| `BWBENCH_SOLVER` | unset | Experimental solver; its environment sets it |
| `BWBENCH_STACK` | set by `scripts/asv.sh` | Stack hash; don't set it |
| `BWBENCH_COMMIT` | checked-out commit | Commit recorded with results |
