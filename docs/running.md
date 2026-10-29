# Running the benchmarks

How to run the benchmarks and the compat checks yourself, and the settings they take. What
they measure is in [method.md](method.md).

You need Docker and [just](https://just.systems). `just results-commit` also needs rsync and
git 2.42 or later. Brightway's code runs only in a throwaway container, the benchmark box; the
[assurance case](assurance-case.md) says what it is allowed to do.

## Benchmarks

```sh
just smoke                       # each package's oldest and latest release, small database
just bench bw2calc               # every bw2calc release listed in asv/bw2calc.hashes
just bench bw2data "4.7^!" -e    # one release; extra arguments go to asv
just site                        # build the history pages in site/
just results-commit              # keep results/ on the local results branch, for publishing
just solver-lci klu ecoinvent    # bw2calc 3.1.0's own lci() with one solver, KLU here
just codspeed bw2calc pypardiso  # one suite under CodSpeed's CPU simulation (instruction counts)
just compat 3.13                 # today's Brightway releases together on one Python, small database
just compat 3.12 floors          # the same, with Brightway's dependencies at their lowest allowed versions
```

Every benchmark runs on the 200-product `smoke` database unless you pick others. For example,
`BWBENCH_SIZES=ecoinvent just bench bw2calc` times the ecoinvent-sized one. The other settings
are in [Environment variables](#environment-variables).

A full-size bw2calc run takes about 24 minutes with the SuperLU environment, and 6 minutes with
`BWBENCH_SOLVERS=pypardiso`. `BWBENCH_ROUNDS=1` halves it. Each result is checked once per
parameter set, not after every sample.

`just bench` skips what already succeeded, so a run that stopped partway resumes.

The `codspeed` workflow runs every suite in `benchmarks/codspeed` the same way on each pull
request and push to `main`, at the smoke size. It uploads the instruction counts to
[CodSpeed](https://app.codspeed.io/simonvanlierde/brightway-benchmarks), which reports any
change on the pull request.

### Experimental solvers

bw2calc has two experimental environments that run only when you name them, as in
`BWBENCH_SOLVERS=klu,umfpack-T`:

- `klu` is KLU, through pyklu, on x86_64 only.
- `umfpack-T` is scikit-umfpack factorizing Aᵀ.

bw2calc cannot pick either, so the suite patches them in where bw2calc binds its solvers
([`src/bwbench/solvers.py`](../src/bwbench/solvers.py)). A case fails if bw2calc never reached
the patch. `FastScoresOnlyMultiLCA` needs PyPardiso or UMFPACK, so `klu` skips it. Its adjoint
direction hands bw2calc's solver Aᵀ, so `umfpack-T` skips that direction too.

### bw2calc on conda-forge's builds

`bw2calc-conda` is the bw2calc suite on conda-forge's builds instead of PyPI's wheels: Python,
NumPy, SciPy, PyPardiso with MKL, and scikit-umfpack with conda-forge's SuiteSparse, on
OpenBLAS and again on MKL's BLAS. They are at the fixed stack's versions
([`asv/bw2calc-conda.json`](../asv/bw2calc-conda.json), asv's `rattler` environments). The
pure-Python rest of the stack still comes from PyPI.

`just bench bw2calc-conda` runs it over the two releases conda-forge has carried since NumPy 2,
2.4.0 and 3.1.0. Its environments are solved when they are built. So the build strings of every
conda package, the BLAS among them, go into a `versions-*.txt` file beside the results. The
PyPI environments have a `pylock.*.toml` lock file instead.

### Measure the noise

`just noise SUBJECT` runs the latest release of SUBJECT 10 times and prints each case's spread
([method.md](method.md#the-noise-floor) has the results). It also writes each sample's CPU
time, wall time and involuntary context switches to `rounds.jsonl`.
`scripts/noise_summary.py` says how to read them.

### Publish results

`just results-commit` refuses results that name this host, since they become public once
pushed. Other names to refuse, such as an ssh alias, go in `BWBENCH_PRIVATE_NAMES`.

## Memory

The box has 2 GB by default and no swap. A job over the limit is killed by the kernel's OOM
killer: under asv that shows as a failed benchmark, otherwise as exit 137. Set `BWBENCH_MEM`
to give it more. bw2calc's first score and bw2data's write record peak memory (`peakmem_` in
asv), so you can see what a case needs.

## Add a release

When a package publishes a new release:

1. Add it to `asv/<package>.hashes`.
2. Move the cutoff in `scripts/in-box.sh`.
3. Run `just stack <package>` to resolve its new fixed set of dependencies.
4. Run `just stack-check <package>`, and drop the releases that no longer run on the new set.

[method.md](method.md#how-the-results-stay-reproducible) says why the set is fixed.

## Compat

`just compat PYTHON [COLUMN]` asks a different question: do the newest releases work together?
It installs the latest brightway25, bw_graph_tools and bw_timex from PyPI into a fresh
environment, with no release cutoff and no fixed stack. Then it runs every case once at the
`smoke` size. A case fails if it errors, its result check fails, or the releases cannot run
it. Nothing is timed.

The column sets what gets installed:

- `latest` (the default): the newest release of everything.
- `floors`: the newest Brightway packages and test harness, with each package they depend on
  directly (NumPy, SciPy, pandas and so on) at the oldest version Brightway says it supports
  that has a wheel. A lower bound set too low fails here. The rest of the dependencies stay at
  their latest, since their own lower bounds say nothing about Brightway. A bound already found
  too low is raised to the oldest release that works, so the run reaches the next one.
  `scripts/compat.sh` lists each, with the package that declares it.
- `pre`: like `latest`, but pre-releases count too, so NumPy, SciPy and pandas betas show
  problems before their release.
- `conda-forge`: the same set from conda-forge, installed with pixi in its container image. It
  installs the Brightway packages conda-forge has, and leaves out the bw_graph_tools and
  bw_timex cases, since neither package is on conda-forge yet. The set goes to `pixi.toml` and
  `pixi.lock`, and its Python packages to `requirements.txt`. Linux only.
- `suites`: like `latest`, plus what the packages' tests need. Then it runs the test suites of
  bw2data, bw2calc, bw2io, bw_processing, matrix_utils, bw_graph_tools and bw_timex instead of
  the benchmarks. A new release of pytest or NumPy that breaks a package's tests shows here the
  day it comes out, before that package's own CI runs again. The tests come from each
  package's GitHub tag for the installed version, since most sdists leave them out. Linux only.

bw_timex pulls in PyPardiso on Linux x86_64, so there bw2calc solves with PyPardiso, not
SuperLU or UMFPACK.

### What a run writes

Each run writes to `.asv/compat/PYTHON-COLUMN/`:

- `requirements.txt`: the versions the run resolved.
- `pylock.toml`: the same set with each wheel's hash, for that job's operating system. Both
  files include pytest.
- For `suites`, `suites.txt` says per package whether it passed, with the failing tests, and
  `suites/PACKAGE.log` holds pytest's output. A test that cannot pass in this run whatever the
  releases would be deselected in `scripts/compat-suites.sh`, with its reason. None is so far.

### The nightly runs

The `compat` workflow runs every night:

| Column | Linux | macOS | Windows |
| --- | --- | --- | --- |
| `latest` | 3.12, 3.13, 3.14 | 3.12 | 3.12 |
| `floors` | 3.12 | | |
| `pre` | 3.14 | | |
| `conda-forge` | 3.12 | | |
| `suites` | 3.12 | | |

Only `latest` turns the run red. The other columns can fail without that, so check their jobs.
Each job's summary lists the versions, and for `suites` each package's result.

On macOS and Windows, the job runs on the runner itself, which cannot run the Linux box. On
macOS the cases that need PyPardiso or UMFPACK skip instead of failing, since neither installs
from PyPI there.

### Install a set that works

The site's [works together today](https://simonvanlierde.com/brightway-benchmarks/#works-together)
table shows how each job ended in the latest nightly run, and the last set that passed. To
install that set, download its `requirements.txt` and use it as constraints:

```sh
uv pip install brightway25 -c requirements.txt
```

For the `conda-forge` row, download its `pixi.toml` and `pixi.lock` into one folder and run
`pixi install --frozen` there. A package conda-forge does not have reads "not on conda-forge"
in that row.

The `site` workflow rebuilds the page daily after the nightly run. A set is kept for 90 days,
as long as GitHub keeps the workflow's artifacts.

## Environment variables

`scripts/box.sh` passes every `BWBENCH_*` variable into the box.

| Variable | Default | What it does |
| --- | --- | --- |
| `BWBENCH_SIZES` | `smoke` | Database sizes for most cases, comma-separated: `smoke`, `ecoinvent`, `mc100k`, `regional`, `exiobase`, `stress-random` |
| `BWBENCH_MC_SIZES` | `smoke` | The same, for bw2calc's Monte Carlo cases |
| `BWBENCH_WRITE_SIZES` | `smoke` | The same, for bw2data's write |
| `BWBENCH_TIMEX_SIZES` | `smoke` | The same, for bw_timex |
| `BWBENCH_ITERATIONS` | `10` | Monte Carlo draws per case |
| `BWBENCH_GROUPS` | `100,1000` | Resource groups for bw_processing's and matrix_utils' cases |
| `BWBENCH_ENTRIES` | `10000,100000` | Entries for bw_processing's entry cases |
| `BWBENCH_STEPS` | `5,20` | Time steps for bw_timex |
| `BWBENCH_SOLVERS` | `superlu,pypardiso,umfpack`; `superlu,umfpack` off x86_64 | Solver environments of bw2calc and bw_graph_tools, plus the experimental `klu` and `umfpack-T`. PyPardiso needs Intel's MKL, which has no wheels off x86_64 |
| `BWBENCH_ROUNDS` | `2` | asv rounds per case |
| `BWBENCH_CPUS` | `2` | CPUs for the box |
| `BWBENCH_MEM` | `2g`; `6g` for `just compat`, `12g` for `just solver-lci` | Memory for the box, with no swap |
| `BWBENCH_THREADS` | `1` | Threads for the BLAS and OpenMP pools the solvers use |
| `BWBENCH_MACHINE` | `box-<slot>`, or `box` without a CPU slot | The machine name asv files results under. A resumed `just bench` skips only what this name already holds |
| `BWBENCH_PRIVATE_NAMES` | empty | Space-separated names that `just results-commit` refuses to publish |
| `BWBENCH_ROUNDLOG` | unset | A file for each sample's CPU time, wall time and context switches; `just noise` sets it |
| `BWBENCH_STRICT` | `1` in `just compat` | A case the installed releases cannot run fails instead of skipping. Set it empty to skip, as the macOS compat job does |
| `BWBENCH_TARGET` | `box` | The Dockerfile stage: `box`, `codspeed` or `conda`. The recipes set it |
| `BWBENCH_SOLVER` | unset | The experimental solver to patch into bw2calc. The `klu` and `umfpack-T` environments set it; `scripts/asv.sh` clears one from your shell |
| `BWBENCH_STACK` | set by `scripts/asv.sh` | A hash of the fixed stack, so a new stack gets new environments. Not for you to set |
| `BWBENCH_COMMIT` | the checked-out commit | The commit recorded with each result. `scripts/box.sh` passes it in, since git cannot see a worktree's `.git` from inside the box |
