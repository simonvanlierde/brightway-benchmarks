# Running the benchmarks

How to run the benchmarks and the compat checks yourself.

## Benchmarks

You need Docker and [just](https://just.systems); `just results-commit` also needs rsync and
git 2.42 or later. Brightway's code only runs inside a throwaway container, never on your
machine.

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

The `codspeed` workflow runs every suite in `benchmarks/codspeed` the same way on each pull
request and push to `main`, at the smoke size, and uploads the instruction counts to
[CodSpeed](https://app.codspeed.io/simonvanlierde/brightway-benchmarks), which reports any
change on the pull request.

Every benchmark runs on the 200-product `smoke` database unless you pick others. For
example, `BWBENCH_SIZES=ecoinvent just bench bw2calc` times the ecoinvent-sized one.
`BWBENCH_SIZES` sets the size for most cases, and three cases have their own variable:
`BWBENCH_MC_SIZES` (Monte Carlo), `BWBENCH_WRITE_SIZES` (bw2data) and `BWBENCH_TIMEX_SIZES`
(bw_timex).
`BWBENCH_SOLVERS` picks the solver environments of bw2calc and bw_graph_tools: `superlu`,
`pypardiso` and `umfpack`, all three by default. PyPardiso needs Intel's MKL, so off x86_64
(an Apple Silicon Mac, say) the default is `superlu,umfpack`. bw2calc has two experimental
environments that run only when you name them, as in `BWBENCH_SOLVERS=klu,umfpack-T`: `klu`
(KLU, through pyklu, x86_64 only) and `umfpack-T` (scikit-umfpack factorizing Aᵀ). bw2calc
cannot pick either, so the suite patches them in where bw2calc binds its solvers
([`src/bwbench/solvers.py`](../src/bwbench/solvers.py)), and a case fails if bw2calc never
reached the patch. `FastScoresOnlyMultiLCA` needs PyPardiso or UMFPACK, so it is skipped
under `klu`; its adjoint direction hands bw2calc's solver Aᵀ, so `umfpack-T` skips that too. A full-size bw2calc run takes
about 24 minutes with the SuperLU environment and 6 with `BWBENCH_SOLVERS=pypardiso`.
asv times each case in 2 rounds by default; `BWBENCH_ROUNDS=1` halves a full-size run.
The box gets 2 CPUs and 2 GB of memory unless `BWBENCH_CPUS` and `BWBENCH_MEM` say otherwise,
and the solvers run on `BWBENCH_THREADS` threads, 1 by default.
`just results-commit` refuses results that name this host, since they become public once
pushed; other names to refuse, such as an ssh alias, go in `BWBENCH_PRIVATE_NAMES`.
Each result is checked once per parameter set, not after every sample.

`bw2calc-conda` is the same bw2calc suite on conda-forge's builds instead of PyPI's wheels:
Python, NumPy, SciPy, PyPardiso with MKL, and scikit-umfpack with conda-forge's SuiteSparse
on OpenBLAS and again on MKL's BLAS, at the fixed stack's versions
([`asv/bw2calc-conda.json`](../asv/bw2calc-conda.json), asv's `rattler` environments). The pure-Python rest of the stack still comes from PyPI.
`just bench bw2calc-conda` runs it over the two releases conda-forge has carried since NumPy 2,
2.4.0 and 3.1.0. Its environments are solved when they are built, so the build strings of
every conda package (the BLAS among them) go into a `versions-*.txt` file beside the results.
The PyPI environments have a `pylock.*.toml` lock file instead.

When a package publishes a new release, `just stack` and `just stack-check` move its fixed
set of dependencies ([Method](method.md#how-the-results-stay-reproducible)) forward; the steps are in the [justfile](../justfile).

`just compat` asks a different question: do the newest releases work together? It installs
the latest brightway25, bw_graph_tools and bw_timex from PyPI into a fresh environment, with
no release cutoff and no fixed stack, and runs every case once at the `smoke` size. A case
fails if it errors, its result check fails, or the releases cannot run it; nothing is timed.
A second argument picks the column, which sets what gets installed:

- `latest` (the default): the newest release of everything.
- `floors`: the newest Brightway packages and test harness, with each package they depend on directly (NumPy,
  SciPy, pandas and so on) at the lowest version their declared bounds allow that has a
  wheel. A lower bound set too low fails here. The rest of the dependencies stay at their
  latest, since their own floors say nothing about Brightway. Floors already found too low
  are raised to the oldest release that worked, so the run reaches the next one:
  `scripts/compat.sh` lists each with the package that declares it.
- `pre`: like `latest`, but pre-releases count too, so NumPy, SciPy and pandas betas show
  problems before their release.
- `conda-forge`: the same set from conda-forge, installed with pixi in its container image.
  conda-forge gets each release only once its feedstock merges the update, so this column
  breaks on its own: bw2calc stayed at 2.4.0 there until 3.1.0 landed on 2026-10-18. It
  installs the Brightway packages conda-forge has, and leaves out the bw_graph_tools and
  bw_timex cases, since neither package is on conda-forge yet. The set goes to `pixi.toml`
  and `pixi.lock`, and its Python packages to `requirements.txt`.
- `suites`: like `latest`, plus what the packages' tests need, and then it runs the test
  suites of bw2data, bw2calc, bw2io, bw_processing, matrix_utils, bw_graph_tools and
  bw_timex instead of the benchmarks. A new release of pytest or NumPy that breaks a
  package's tests shows here the day it comes out, before that package's own CI runs again.
  The tests come from each package's GitHub tag for the installed version, since most
  sdists leave them out. `.asv/compat/PYTHON-suites/suites.txt` says per package whether
  it passed, with the failing tests, and `suites/PACKAGE.log` holds pytest's output.
  A test that cannot pass in this run whatever the releases would be deselected in
  `scripts/compat-suites.sh`, with its reason; none is so far. Linux only.

For example, `just compat 3.12 floors`. bw_timex pulls in PyPardiso on Linux x86_64, so there
bw2calc solves with PyPardiso, not SuperLU or UMFPACK. The versions each run resolved go to
`.asv/compat/PYTHON-COLUMN/requirements.txt`, and the same set with each wheel's hash to
`pylock.toml` beside it. The `compat` workflow runs `latest` every night
on Linux with Python 3.12, 3.13 and 3.14 and on macOS and Windows with 3.12, `floors`,
`conda-forge` and `suites` on 3.12 on Linux and `pre` on 3.14, and lists the versions (and for
`suites`, each package's result) in each job's summary. On macOS and Windows it runs
on the runner itself, which cannot run the Linux box. On macOS the cases that need PyPardiso
or UMFPACK skip instead of failing, since neither installs from PyPI there. `floors`, `pre`,
`conda-forge` and `suites` can fail without turning the run red, so check their jobs.

The [site](https://simonvanlierde.com/brightway-benchmarks/#works-together) has a
"works together today" table: how each job ended in the latest nightly run, and the last
set that passed, with its Brightway and NumPy versions and its `requirements.txt` and
`pylock.toml`. To install a set known to work, use its `requirements.txt` as constraints, as
in `uv pip install brightway25 -c requirements.txt`. For the `conda-forge` row, download its
`pixi.toml` and `pixi.lock` into one folder and run `pixi install --frozen` there; a package
conda-forge does not have reads "not on conda-forge" in that row. The `site` workflow rebuilds the page
daily after the nightly run, and a set is kept for 90 days, as long as GitHub keeps the workflow's artifacts.

## Memory

bw2calc's first score and bw2data's write also record peak memory (`peakmem_` in asv). The box
has 2 GB by default and no swap, so a job over the limit is killed by the kernel's OOM killer:
under asv that shows as a failed benchmark, otherwise as exit 137. Set `BWBENCH_MEM` to give it
more.
