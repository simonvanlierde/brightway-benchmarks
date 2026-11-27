# Running the benchmarks

- [Install a tested Brightway set](#install-a-set-that-works) for your operating system and Python.
- [Reproduce a release timing](#benchmarks) with the published benchmark case.
- [Contribute a run](#contribute-a-run) to see how solvers compare on your machine.

## Benchmarks

Install Docker and [just](https://just.systems), then run these commands from a clone of this
repository. Benchmarks run in a throwaway container called the box
([where it runs](architecture.md#where-it-runs)).

```sh
just smoke                    # oldest and latest release of each package, small database
just bench bw2calc            # all releases in asv/bw2calc.hashes
just bench bw2data "4.7^!" -e  # one release, with extra arguments passed to asv
```

To reproduce the first-score comparison in the solver story, use the synthetic ecoinvent-sized
database and select bw2calc 3.1.0 and the first-score case:

```sh
BWBENCH_MACHINE=noise BWBENCH_SIZES=ecoinvent just bench bw2calc-conda "3.1.0^!" --bench SingleScore.time_first_score
```

Compare the `LCA` rows with the published timings in the
[solver story](https://simonvanlierde.com/brightway-benchmarks/stories/solver-choice/).
It lists the measured stack and machine settings. This rerun stays in `.asv/noise/`.
Use [`scripts/solver_factorize.py`](../scripts/solver_factorize.py) with a licensed copy of
ecoinvent 3.12 cut-off to reproduce its separate factorization measurements.

`just` lists the recipes. For example, `just release-changes bw2calc` shows changes in the latest
release and `just solver-lci klu ecoinvent` times `lci()` with KLU.

Cases default to the 200-product `smoke` database. Set `BWBENCH_SIZES=ecoinvent` for a
full-size run. For bw2calc it takes about 24 minutes, or 6 with `BWBENCH_SOLVERS=pypardiso`.
Keep the default two rounds. In the larger bw2calc cases, one round raised the median
run-to-run spread from 0.6% to 2.1%. The bw_processing and bw_timex cases stayed under
0.4% either way.

`just bench` skips successful cells, so interrupted runs resume. After a generator update,
`just bench-lines bw2calc` can time the newest release in each minor line and the untagged
releases first. A later `just bench bw2calc` fills the rest.

### Inspect a benchmark

- `just release-changes bw2calc` shows what moved in the latest release.
- `just solver-lci klu ecoinvent` times `lci()` with KLU.
- `just codspeed bw2calc pypardiso` measures CPU instructions as the
  [CodSpeed workflow](https://app.codspeed.io/simonvanlierde/brightway-benchmarks) does.
- `just profile` profiles one call with pyinstrument. Give the `@bench` function name,
  release (defaults to latest), extra packages and every case parameter:

  ```sh
  just profile bw2calc first_score release=3.0.0 with=scikit-umfpack size=ecoinvent cls=IterativeLCA
  ```

Profiles go to `.asv/profiles/` as HTML and speedscope JSON. To publish a profile with a
finding, copy the HTML to `profiles/` and set the finding's `profile` in
[`benchmarks/findings.toml`](../benchmarks/findings.toml).

### Preview and save results

Run `just ui-serve` to preview the UI at `127.0.0.1:4400`. To prepare site data, run `just site`
for the compat archive and redirects, then `just ui-data site/data` for timing histories,
guidance and ratios. Add new benchmark descriptions to
[`benchmarks/descriptions.toml`](../benchmarks/descriptions.toml). The export warns about missing entries.

`just results-commit` saves timings on the local `results` branch. It needs
[uv](https://docs.astral.sh/uv/), rsync and Git 2.42 or later. It refuses private machine
names (including `BWBENCH_PRIVATE_NAMES`), new or changed results without
[fingerprints](method.md#how-the-results-stay-reproducible), and runs with no successful
new cells. Keep the default threads, rounds, CPUs and memory for anything you commit.
ASV results omit those settings.

To remove a result, edit or delete it in a `results` branch worktree. Run the main branch's
`scripts/run_crate.py` against that worktree and commit the change with the rebuilt
`ro-crate-metadata.json`. An omitted file or cell in a regular run leaves earlier data in place.

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

With uv installed, `just noise SUBJECT` runs the latest release of SUBJECT 10 times and
prints each case's [spread](method.md#the-noise-floor). Each sample's CPU time, wall time and
context switches go to `rounds.jsonl` for `scripts/noise_summary.py`.

### Hosted ratios

`just ratios COMPARISON...` runs `bwbench compare` in the box: interleaved ratios between
solvers, install paths, Pythons or releases ([method.md](method.md#hosted-ratios)). It writes
`.asv/ratios/box.json`, which no history or site page reads. With no COMPARISON it runs
`solvers`; `all` runs every comparison this OS has. The box has no pixi, so its `install-path`
arm from conda-forge is missing. The `ratios` workflow runs `all` weekly on GitHub's runners.

### The nightly canary

`just canary` times a fixed workload in the box: a pure-Python loop and a 64 MiB memory copy,
15 samples each, standard library only. Its code never changes, so a move in its time means the
machine drifted, not Brightway. Each night writes `results/canary/<machine>/<time>.json` with the
samples, their medians and the fingerprint. `just results-commit` puts it on the `results` branch,
apart from the histories. `just canary-check` compares the newest night with up to 14 before it
and exits 1 when a median moved by more than the larger of 3% and three times the earlier nights'
spread. It exits 2 when there is no canary file yet. It
also prints each fingerprint field that changed since the night before, such as a new kernel.
The benchmark node runs all three nightly.

#### Energy per operation

On an Intel CPU, `BWBENCH_ENERGY=1` adds each sample's energy in joules to `rounds.jsonl`. It is
read from the CPU's RAPL package counter, so your user needs read access to
`/sys/class/powercap/intel-rapl:0/energy_uj`.

The counter covers the whole CPU package, all cores and every process, so the run needs a quiet
machine, and the joules per sample include what the idle CPU draws anyway. To get the energy the
operation adds, sample the idle draw first and then run the benchmark, both inside one quiet gate
with no other work running:

```sh
export BWBENCH_CPUSET=0-7 BWBENCH_GATE_CPUS=0-7
bwbench-gate sh -c 'python3 scripts/idle_energy.py .asv/idle-energy.json &&
    BWBENCH_ENERGY=1 just noise bw2calc 3'
python3 scripts/energy_summary.py .asv/noise/bw2calc/rounds.jsonl \
    --idle-w "$(jq .idle_w .asv/idle-energy.json)"
```

`scripts/idle_energy.py` samples for five minutes, sums five-second counter deltas across wraps,
and writes the measured `idle_w` to JSON; the summary subtracts it from each sample. A timed
sample's energy is summed the same way, from readings five seconds apart. When a reading fails or
comes over 60 seconds after the last, the counter may have wrapped unseen, so that sample logs no
energy.

An energy run always uses the plain `docker run`, never a host's `BWBENCH_RUNNER`, pinned to the CPUs
in `BWBENCH_CPUSET`. It runs through a quiet gate: `BWBENCH_GATE`, or `bwbench-gate` on `PATH`, a
program that runs `GATE CMD...` once no other work runs on the CPUs in `BWBENCH_GATE_CPUS`, which
`box.sh` sets to `BWBENCH_CPUSET`. An outer gate, as above, protects the same CPUs. Without a gate
and `BWBENCH_CPUSET`, `box.sh` refuses the run.

A bench run logs energy too when it names a log, as in
`BWBENCH_ENERGY=1 BWBENCH_MACHINE=noise BWBENCH_ROUNDLOG=/src/.asv/energy.jsonl just bench bw2calc "3.1.0^!"`.
`BWBENCH_MACHINE=noise` keeps its timings out of `results/`. The round logs stay local; they never
go to `results/` or the site's benchmark history.

## Memory

The box has 2 GB and no swap by default. A job over the limit is killed: under asv as a failed
benchmark, otherwise with exit 137. Set `BWBENCH_MEM` to give it more.

The box's `/tmp` is a tmpfs of up to 6 GB, and what lands there counts against that memory:
bw2data's and bw_timex's projects and extracted archives. A bw2data write at the ecoinvent size
needs more than the 2 GB default. The venvs of `just codspeed`, `just profile` and `just compat`
live under `.asv/venvs/` on disk.

asv's own environments, in `.asv/env/`, only grow: one per subject and matrix entry, about 300 MB
each, kept after the entry leaves the config. `just tidy-envs` removes those asv has not used in 30
days (by the access time of each one's `asv-install-status.json`) and hardlinks identical files
across the rest; the night queue runs it after its last job. It skips a subject whose asv run
holds the lock, and an asv run started while it works on that subject fails at once.

## Add a release

1. Add it to `asv/<package>.hashes`.
2. Move the cutoff in `scripts/in-box.sh`.
3. Run `just stack <package>` to resolve the new fixed set of dependencies. Its first line names
   the cutoff it was resolved at, and the tests fail when that is later than the one in
   `scripts/in-box.sh`. Other packages' sets keep their older cutoff until they are resolved again.
4. Run `just stack-check <package>`, and drop the releases that no longer run on it.

[method.md](method.md#how-the-results-stay-reproducible) says why the set is fixed.

Hash-only entries in `asv/<package>.hashes` are experiments. They stay in the history, but
the viewer and `just release-changes` compare release tags only.

## Compat

`just compat PYTHON [COLUMN]`, as in `just compat 3.13 floors`, asks whether the newest
releases work together. It installs the latest brightway25, bw_graph_tools and bw_timex into a
fresh environment and runs every case once at the `smoke` size, untimed.

- `latest` (default): the newest release of everything.
- `floors`: Brightway's direct dependencies at the oldest version Brightway allows that has a
  wheel. A bound already found too low is raised to the oldest release that works, as listed in
  `scripts/compat.sh`.
- `pre`: like `latest`, with pre-releases.
- `conda-forge`: the same set from conda-forge with pixi, without the bw_graph_tools and
  bw_timex cases, on Linux, macOS and Windows.
- `suites`: like `latest`, but runs the test suites of bw2data, bw2calc, bw2io, bw_processing,
  matrix_utils, bw_graph_tools and bw_timex, from each package's GitHub tag.

bw_timex pulls in PyPardiso on Linux x86_64 and 64-bit Windows, so there bw2calc solves with PyPardiso.

Each run writes to `.asv/compat/PYTHON-COLUMN/`: `requirements.txt`, and `pylock.toml` with
each wheel's hash for that job's operating system. `pylock.toml` says `requires-python >=3.13`,
so an older patch release such as 3.13.0 can use it. `conda-forge` also writes
`environment.yml` (every conda package of the user environment at its locked version; pytest
lives in a separate pixi `test` environment), `pixi.toml` and `pixi.lock`. `suites` writes
`suites.txt` with each package's result and `suites/PACKAGE.log`.

### The nightly runs

The `compat` workflow runs 30 nightly checks across the five columns, three operating
systems and Python 3.13 and 3.14. Only `latest` can fail the workflow. All failures show
in the published table. Linux runs in containers, macOS and Windows on their runners.
macOS PyPI checks skip solver cases that require PyPardiso or UMFPACK.

After a coverage change merges, dispatch `compat` on `main`, wait for `archive`, then
dispatch `site`. A run on a feature branch leaves the archive unchanged.

### The compat archive

On `main`, `scripts/compat_site.py` writes the last passing sets to the `compat` branch.
When a set changes, it gets a dated folder under `compat/COLUMN-PYTHON-OS/` that stays
after the run's artifacts expire. The undated folder follows the latest passing set.
Its `set.json` records the latest passing date and run even when the set is the same.
`compat/status.json` records every job's outcome. `just site` copies the archive
to `site/compat` for publishing.

### Which Pythons work

The compat jobs need Python 3.13 or later, as the harness does. For other Pythons,
`scripts/py_probe.py` checks whether packages install and import and a two-process LCA
gives the right score. It uses today's releases and needs only uv:

```sh
uv run --no-project --python 3.13 scripts/py_probe.py 3.12 .asv/probe/3.12
```

The probe writes `probe.json` with each step and `requirements.txt` with the installed
set. It exits 1 on failure. If no release declares that Python, the install step says
`"declared": false` and skips the imports. Read the step's error before reporting a failure.

The `python-probe` workflow runs daily for Python 3.11 to 3.15 on all three OSes, and
on Mondays for the end-of-life 3.9 and 3.10 on Linux. The job summary lists each step.
The site exports the latest main-branch artifacts (`scripts/probe_site.py` and
`scripts/export_guidance.py --probe`). Setup shows supported Python versions, and
Benchmarks includes the end-of-life versions.

### Install a set that works

On the [Setup page](https://simonvanlierde.com/brightway-benchmarks/),
select your operating system, Python and installer. Check the date and scope of the last
passing set, then copy the command for your tool. The smoke checks run small calculations.
The `suites` checks run the packages' full test suites.

Use the dated URL to install the same versions later. Use the undated URL to install the
newest passing set.

```sh
uv add brightway25 bw_graph_tools bw_timex -c URL/requirements.txt
pip install brightway25 bw_graph_tools bw_timex -c URL/requirements.txt
conda env update -n brightway-tested -f URL/environment.yml --prune
curl -fL -O URL/pixi.toml -O URL/pixi.lock && pixi install --frozen
```

The first two use the runtime libraries the PyPI compatibility job checks together.
Constraints pin versions but do not install packages themselves. `uv add` adds them to the
project in the current folder, so it needs a `pyproject.toml` whose `requires-python` starts at
the set's Python version or later: uv resolves for every Python the project allows. The full
requirements file also includes the test harness; `uv pip install -r requirements.txt` installs
that complete recorded environment. The conda command creates the `brightway-tested`
environment if it is missing and is safe to rerun; `--prune` removes anything else in it, so
keep your own packages in another environment. The conda and pixi commands use the
`conda-forge` row.

## Contribute a run

You can add your machine's ratios: how much faster UMFPACK and PyPardiso solve an LCA than
SuperLU there (on a Mac also Apple Accelerate's sparse LU), and with `install-path` how bw2calc from conda-forge compares with PyPI. A
contribution is one result file from `bwbench compare`
([method.md](method.md#hosted-ratios)). It holds ratios between set-ups timed in turn on one
machine, so your machine's speed and noise largely cancel out. The comparison page marks
contributed rows as unverified. It uses them in a summary only when there are no reference or
hosted measurements for that option.

The run installs bw2calc and its solvers from PyPI into new virtual environments in a
temporary folder, and runs them on your machine, outside any container. You need
[uv](https://docs.astral.sh/uv/) and [git](https://git-scm.com/). On macOS, run
`brew install suite-sparse swig` first, or the UMFPACK arm is recorded as missing. The Accelerate
arm compiles a small C file against Apple's SDK, so it needs macOS 15.5 or newer and the Xcode
Command Line Tools (`xcode-select --install`); without them it is missing too. PyPardiso
installs only on x86_64; elsewhere its arm is missing too, which is a result, not an error.

1. Plug a laptop in, set its performance power mode and close other work.
2. Run the solvers comparison. At 20 rounds it takes about a minute, plus the downloads on
   the first run:

   ```sh
   uvx --from git+https://github.com/simonvanlierde/brightway-benchmarks bwbench compare --machine "Apple M3 Pro" -o result.json
   ```

   Set `--machine` to a label for the machine, such as its CPU model, never its host name.
   The label needs ASCII letters or digits, which name its folder. Without it, the CPU model is used. Add `install-path` to the command to time conda-forge
   against PyPI too; that needs [pixi](https://pixi.sh).
3. Fork this repository, then copy the file to
   `ratios/contributed/<machine>/<date>.json`. `<machine>` is your label in lower case with
   dashes (`apple-m3-pro`), and `<date>` is the day in the file's `created` field
   (`2026-11-14`).
4. Check it before you commit:

   ```sh
   uvx --from git+https://github.com/simonvanlierde/brightway-benchmarks bwbench validate --contribution ratios/contributed/apple-m3-pro/2026-11-14.json
   ```

   It exits 0 when the file can go in. It refuses a file that is not in its folder, that
   says a tier other than `contributed`, has a default host name as its label (such as
   `Ada's MacBook Pro`, `ada-ThinkPad-X1` or `DESKTOP-4F2K9QX`), names a user folder, or is over 256 KiB.
5. Commit with `git commit -s`
   ([CONTRIBUTING](../.github/CONTRIBUTING.md#sign-off-your-commits)) and open a pull request
   against `main`. Add `?template=contribute-a-run.md` to the address of the "Open a pull
   request" page to get its checklist. The `contributed` workflow runs the same check.

The file records the CPU model, OS, kernel, Python, BLAS and the installed versions, never a
host name or user name. Read it before you push: a `missing` reason holds the last lines of an
installer's error, with your home folder and any other user folder written as `~`.

## Publish the synthetic inputs

`just dataset` writes the synthetic systems at the current generator version to
`.asv/dataset-v<version>/`, for a Zenodo deposit: per generated profile, at seed 0, a zip of its
bw_processing datapackages with the reference scores, and a zip of its ecoSpold2 release. Beside
them are a dataset card (`README.md`), `metadata.json` (every profile's fields) and `SHA256SUMS`
(the checksum of each file). `just dataset smoke ecoinvent` writes only those profiles. An
existing folder is never overwritten, and a failed run leaves none: it builds in a `.partial`
folder and renames it at the end. The whole set needs about 12 GB of memory and 34 GB of disk in
`.asv/` for `regional`; name smaller profiles to skip it.

It refuses what may not ship and, when anything is refused, lists it in
`.asv/dataset-v<version>-review/excluded.json`, outside the archive: the BAFU and USEEIO profiles, which are read from real archives, not
generated. The ecoSpold2 files use flow UUIDs derived from the generator's own namespace, not
biosphere3's, and each file is scanned before it is zipped: a UUID that is not name-based
(version 5) or one of the two unit ids, or "ecoinvent" outside the format's namespace, stops the
build. Uploading stays a manual step: create a new version of the record, check the DataCite
fields, then publish.

## Environment variables

`scripts/box.sh` passes every `BWBENCH_*` variable into the box.

| Variable | Default | What it sets |
| --- | --- | --- |
| `BWBENCH_SIZES` | `smoke` | Database sizes: `smoke`, `ecoinvent`, `mc100k`, `regional`, `exiobase`, `stress-random`, `useeio`, `bafu` (real data, downloaded once; [method.md](method.md#the-real-databases)) |
| `BWBENCH_MC_SIZES` | `smoke` | Sizes for bw2calc's Monte Carlo |
| `BWBENCH_WRITE_SIZES` | `smoke` | Sizes for bw2data's write |
| `BWBENCH_TIMEX_SIZES` | `smoke` | Sizes for bw_timex |
| `BWBENCH_ITERATIONS` | `10` | Monte Carlo draws per case |
| `BWBENCH_GROUPS` | `100,1000`; `100,1000,10000` when `BWBENCH_SIZES` holds anything but `smoke` alone | Resource groups (bw_processing, matrix_utils) |
| `BWBENCH_ENTRIES` | `10000,100000` | bw_processing entries |
| `BWBENCH_STEPS` | `5,20` | bw_timex time steps |
| `BWBENCH_SOLVERS` | `superlu,pypardiso,umfpack` (no `pypardiso` off x86_64) | Solver environments |
| `BWBENCH_ROUNDS` | `2` | asv rounds per case |
| `BWBENCH_CPUS` | `2` | CPUs for the box |
| `BWBENCH_MEM` | `2g` (a runner's own default under `BWBENCH_RUNNER`); `6g` compat, `12g` solver-lci | Box memory, no swap |
| `BWBENCH_RUNNER` | `bwbench-runner` on `PATH`, if any | A host's own program for the box, such as a CPU-slot runner; empty for the plain `docker run`. Its contract is at the top of `scripts/box.sh` |
| `BWBENCH_GATE` | `bwbench-gate` on `PATH`, if any | Quiet gate for energy runs |
| `BWBENCH_CPUSET` | none | CPUs an energy run is pinned to |
| `BWBENCH_THREADS` | `1` | BLAS and OpenMP threads |
| `BWBENCH_MACHINE` | `box-<slot>` or `box` | asv machine name; resume needs the same one |
| `BWBENCH_PRIVATE_NAMES` | empty | Names `just results-commit` refuses |
| `BWBENCH_ROUNDLOG` | unset | Per-sample log; `just noise` sets it |
| `BWBENCH_STRICT` | `1` in compat | Fail, not skip, a case the installed releases cannot run; a case for another solver still skips |
| `BWBENCH_TARGET` | `box` | Dockerfile stage; recipes set it |
| `BWBENCH_SOLVER` | unset | Experimental solver; its environment sets it |
| `BWBENCH_STACK` | set by `scripts/asv.sh` | Stack hash; don't set it |
| `BWBENCH_COMMIT` | checked-out commit | Commit recorded with results |
| `BWBENCH_HIDE` | unset | Modules (comma-separated) `bwbench compare` hides from a case, such as `pypardiso` for its SuperLU arm; it sets it |
| `BWBENCH_PROFILE_WITH` | set by `just profile` | Packages installed on top, for the profile's name; don't set it |
| `BWBENCH_RAPL` | `/sys/class/powercap/intel-rapl:0` | RAPL counter folder for energy runs; the tests point it at a fake |
| `BWBENCH_GATE_CPUS` | set by `scripts/box.sh` | CPUs it hands the quiet gate; read by the gate, don't set it |
