# brightway-benchmarks

[![python](https://github.com/simonvanlierde/brightway-benchmarks/actions/workflows/python.yml/badge.svg)](https://github.com/simonvanlierde/brightway-benchmarks/actions/workflows/python.yml)
[![license](https://img.shields.io/badge/license-BSD--3--Clause-blue.svg)](LICENSE)
[![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/simonvanlierde/brightway-benchmarks/badge)](https://scorecard.dev/viewer/?uri=github.com/simonvanlierde/brightway-benchmarks)

How fast is [Brightway](https://docs.brightway.dev), and does it still give the right answer?
This repository times the calculations an LCA practitioner runs every day, across
Brightway's released versions: an LCI and LCIA, many functional units at once, Monte Carlo.
It also checks every result against an independent reference score. A release that makes a
calculation slower, or quietly changes a score, shows up here.
The results so far are on the
[benchmark history pages](https://simonvanlierde.github.io/brightway-benchmarks/).

No licensed data is used. The benchmarks run on synthetic databases that copy the structure
of ecoinvent, so anyone can rerun them and the results can be published.

## What is measured

| Package | What is timed, in LCA terms |
| --- | --- |
| bw2calc | One score (build the matrices, solve, characterize); a second functional unit on a solved system; many functional units against three impact categories; Monte Carlo draws; a cold `import bw2calc` |
| bw2data | Writing a database, up to the size of ecoinvent; a cold `import bw2data` |
| bw_processing, matrix_utils | Building datapackages and matrices from many resource groups |
| bw_graph_tools | Supply-chain graph traversal, small and large |
| bw_timex | The time-explicit LCI as the timeline grows |

bw2calc runs each case with the direct solvers (PyPardiso, UMFPACK, SuperLU) and with its
iterative solvers.

Each benchmark checks its score next to the timing, against a reference that uses no
Brightway code at all. So a fast but wrong release fails instead of looking good. Only the
bw_processing cases that build datapackages from entries have nothing to check, and neither do
the import cells.

bw2calc's first score and bw2data's write also record peak memory (`peakmem_` in asv). The box
has 2 GB by default and no swap, so a job over the limit is killed by the kernel's OOM killer:
under asv that shows as a failed benchmark, otherwise as exit 137. Set `BWBENCH_MEM` to give it
more.

## The synthetic databases

A database is generated from a seed, so the same settings give the same matrices on every
machine. Its shape comes from a profile:

- `ecoinvent` has 26,533 products, like ecoinvent 3.12 cut-off, and copies that release's
  measured structure: how many inputs each process has and how many consumers each product
  has; one large loop that holds 64% of the products; waste treatments with negative
  inputs; units that span many orders of magnitude; and a spectral radius of 0.78, which
  sets how fast the supply-chain series converges. Only aggregate statistics of ecoinvent
  went into it, calculated from the ecoinvent database (ecoinvent Association), never a
  dataset or a figure of a single dataset. They are in [`src/bwbench/profiles/`](src/bwbench/profiles).
- `smoke` is the same structure at 200 products, for quick checks.
- `mc100k` and `regional` scale it to 100,000 and 250,000 products, the sizes of a large
  Monte Carlo study and a regionalised database.
- `exiobase` and `stress-random` use a random structure, a worst case for the solvers.

One known difference: a direct solver needs more memory and time for the `ecoinvent`
profile than for the real ecoinvent. SuperLU's factors hold 323 times as many entries as
the matrix, against 175 for ecoinvent. The likely cause: the real database's suppliers
share more of their consumers. [#54](https://github.com/simonvanlierde/brightway-benchmarks/issues/54) tracks the work on it.
With a licence of your own, [`scripts/solver_factorize.py`](scripts/solver_factorize.py) times
each direct solver on the real ecoinvent matrix instead, and prints timings only.

## Running it

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
```

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
([`src/bwbench/solvers.py`](src/bwbench/solvers.py)), and a case fails if bw2calc never
reached the patch. `FastScoresOnlyMultiLCA` needs PyPardiso or UMFPACK, so it is skipped
under `klu`; its adjoint direction hands bw2calc's solver Aᵀ, so `umfpack-T` skips that too. A full-size bw2calc run takes
about 24 minutes with the SuperLU environment and 6 with `BWBENCH_SOLVERS=pypardiso`.
asv times each case in 2 rounds by default; `BWBENCH_ROUNDS=1` halves a full-size run.
Each result is checked once per parameter set, not after every sample.

`bw2calc-conda` is the same bw2calc suite on conda-forge's builds instead of PyPI's wheels:
Python, NumPy, SciPy, PyPardiso with MKL, and scikit-umfpack with conda-forge's SuiteSparse
on OpenBLAS and again on MKL's BLAS, at the fixed stack's versions
([`asv/bw2calc-conda.json`](asv/bw2calc-conda.json), asv's `rattler` environments). The pure-Python rest of the stack still comes from PyPI.
`just bench bw2calc-conda` runs it over the two releases conda-forge has carried since NumPy 2,
2.4.0 and 3.1.0. Its environments are solved when they are built, so the build strings of
every conda package (the BLAS among them) go into a `versions-*.txt` file beside the results.
The PyPI environments have a `pylock.*.toml` lock file instead.

When a package publishes a new release, `just stack` and `just stack-check` move its fixed
set of dependencies (below) forward; the steps are in the [justfile](justfile).

`just compat` asks a different question: do the newest releases work together? It installs
the latest brightway25, bw_graph_tools and bw_timex from PyPI into a fresh environment, with
no release cutoff and no fixed stack, and runs every case once at the `smoke` size. A case
fails if it errors, its result check fails, or the releases cannot run it; nothing is timed.
bw_timex pulls in PyPardiso on Linux x86_64, so bw2calc solves with PyPardiso here, not SuperLU
or UMFPACK. The versions it resolved go to `.asv/compat/PYTHON/requirements.txt`. The
`compat` workflow runs it every night on Python 3.12, 3.13 and 3.14 and lists the versions in
each job's summary.

## Results so far

The history pages are at <https://simonvanlierde.github.io/brightway-benchmarks/>.
So far they hold all 15 bw2calc releases from 2.0 to 3.1.0 on the ecoinvent-sized database.
2.1.1 has no git tag, so it shows up under its commit, `a71ede78`.
The other five packages are there too; [The other packages](#the-other-packages) has what they show.
Each case ran on one thread, on an efficiency core of an Intel i9-14900KF.

| Solver | Time for one score with `LCA`, in every release |
| --- | --- |
| SuperLU (SciPy) | 27.7 s |
| PyPardiso | 10.0 s |
| UMFPACK | 9.05 s |

- **No release changed `LCA`'s time for one score.** Two points stood out after one round:
  2.0.2 with SuperLU (34.4 s) and 2.1.1 with PyPardiso (11.6 s). Rerun with two rounds next
  to a neighbouring release, both came back in line: 2.0.2 at 27.8 s against 27.7 s for
  2.0.1, and 2.1.1 at 10.0 s against 10.9 ± 1 s for 2.2. So both were noise, not
  regressions. A single PyPardiso round can come out about 10% slow, as 2.2 did here. The
  third, 2.2's SuperLU `IterativeLCA` at 29.3 s, came back at 27.6 s.
  Across all the releases the times vary by 0.3% (the middle half of the points, relative to
  the median) with every solver, so that's about the smallest step the history can show.
- **Warming up before the timed call changes nothing.** Each case solves once before it's
  timed, as an early check. A first score in a fresh process takes the same time as one
  after that warm-up: 19.2 against 19.1 s with SuperLU, 5.46 against 5.47 s with UMFPACK,
  timed on a faster core than the history. PyPardiso would score in 0.09 s instead of 5.2 s
  if its factorization of the same matrix were kept, so the harness drops it before every
  timed call.
- **Almost all the time goes into the LU factorization.** Under PyPardiso it's 98% of one
  score and 99% of a Monte Carlo draw. Speeding up anything else in bw2calc can't help
  much. Reusing PARDISO's reordering from one draw to the next saves about 2%.
- **`JacobiGMRESLCA`** (from 2.4.0) gives a score in 150 ms, with a relative error of
  1.4e-9. That's on this synthetic matrix only; I haven't checked it on
  ecoinvent.
- **bw2calc 3.0.0 made `IterativeLCA` much slower without PyPardiso, and 3.1.0 fixed it.**
  In 3.1.0 one score takes 27.9 s with SuperLU and 9.05 s with UMFPACK again, as in 2.5.0,
  and `LCA.lci(factorize=True)` takes 27.7 s and 9.05 s. 3.1.0 factorizes Aᵀ wherever it
  factorizes once and solves many times
  ([brightway2-calc#180](https://github.com/brightway-lca/brightway2-calc/pull/180)). In 3.0.0, one score took
  45.0 s with UMFPACK, against 9.04 s in 2.5.0, and about 4 minutes with SuperLU, against
  27.7 s. asv's 600 s limit covers a warm-up run too, so it cut the SuperLU case off.
  `LCA` didn't change. Without PyPardiso, 3.0.0's `IterativeLCA` calls `factorized(matrix.tocsc())`, which factorizes A, the slow way
  round for both solvers ([`iterative_lca.py`](https://github.com/brightway-lca/brightway2-calc/blob/3.0.0/src/bw2calc/iterative_lca.py#L388)).
  `LCA.lci(factorize=True)` makes the same call and takes 45.0 s with UMFPACK, the same
  time as `IterativeLCA`, and 237 s with SuperLU.
- **The UMFPACK line uses reference BLAS.** scikit-umfpack has no wheels, so it builds
  against the SuiteSparse in the benchmark image, which links Debian's reference BLAS.
  With OpenBLAS in its place, one score takes 2.6 s instead of 9.0 s. scikit-umfpack from
  conda-forge links OpenBLAS, and `bw2calc-conda` measures the same 2.63 s (below).
- **On conda-forge's builds only UMFPACK changes.** `bw2calc-conda` against the PyPI stack,
  run the same night on the same commits, two rounds each, `LCA` on the ecoinvent-sized database:

  | Case | Solver | PyPI 3.1.0 | conda-forge 3.1.0 | PyPI 2.4.0 | conda-forge 2.4.0 |
  | --- | --- | --- | --- | --- | --- |
  | One score | SuperLU | 27.8 s | 27.7 s | 27.7 s | 27.6 s |
  | One score | PyPardiso | 10.1 s | 10.0 s | 10.0 s | 10.0 s |
  | One score | UMFPACK | 9.06 s | 2.63 s | 9.06 s | 2.63 s |
  | Second functional unit | UMFPACK | 33.6 ms | 42.7 ms | 51.4 ms | 63.2 ms |
  | `import bw2calc` | PyPardiso | 825 ms | 755 ms | 824 ms | 753 ms |

  UMFPACK's first score is 3.4x faster on OpenBLAS, but a solve on the stored factorization
  (`time_redo_lci`) is 23 to 27% slower. PyPardiso, on conda-forge's MKL 2026.1.0, and
  SuperLU stay within 1%, and so does peak memory. Importing bw2calc with PyPardiso is
  70 ms faster, and about 15 ms slower without it. Scores are identical.

  On MKL's BLAS (`libblas=*=*_mkl`, MKL 2026.1.0) UMFPACK's first score takes 2.45 s, 7%
  less than on OpenBLAS. The second functional unit still takes 42.7 ms on both, so the
  slower solve comes with conda-forge's builds, not with the BLAS. On the real ecoinvent
  3.12 matrix (`solver_factorize.py`, same core, two rounds) UMFPACK factorizes in 1.79 s
  on reference BLAS, 0.66 s on OpenBLAS and 0.63 s on MKL: 2.7x and 2.8x, less than the
  3.4x and 3.7x on the generated database. One solve takes 16.5 ms on PyPI's build and 24 ms on
  both conda-forge builds, so the slower solve holds on real data too.

### The other packages

Every release of bw_processing, matrix_utils and bw_graph_tools, bw2data from 4.6 and
bw_timex from 1.1.0, on the same core. bw_graph_tools ran at the ecoinvent and EXIOBASE
sizes, the others at the ecoinvent size.

- **bw2data 4.7 lost the faster database write it gained two commits earlier.** Writing
  the database takes 15.4 s in 4.6 and 4.6.2. #268 (raw SQLite `executemany`) brings it to
  10.5 s, and the next commit, #270 ("Fix unclosed sqlite3 connections"), takes that code
  path out again, so 4.7 writes in 15.3 s. A rerun with asv's `--interleave-rounds` (six
  rounds, each round going through all four commits) gives 15.3, 10.4, 15.4 and 15.3 s, with
  every 75th percentile within 0.1 s of its median. Runs that time one commit after
  another drift between commits instead: one put 4.6.2 at 21.2 s. 4.8 still writes with
  peewee's batches: interleaved the same way, 4.7 takes 15.4 s, #298's parent 15.6 s, #298
  (which skips VACUUM when the database was empty) 15.1 s and 4.8 15.1 s. The finding is
  reported upstream as brightway2-data#306. The score after the write is off by 5.7e-8 in
  every release.
- **bw_timex 1.3.0 made the time-explicit LCI about 19 times slower.** With 5 time steps
  it takes 25.9 s in 1.2.0, 8.4 minutes in 1.3.0, 13.4 s in 1.3.2 and 3.3 s in 1.4.0 (which
  solves technosphere blocks by a Neumann series); with 20 steps 34.1 s, 7.9 minutes,
  19.3 s and 9.3 s. It isn't c3af060 in 1.3.2 (per-block LU instead of PARDISO
  thrashing): its parent already takes 13.3 s. The slowdown comes in with 46c272a and
  894a4dd, which solve background unit LCIs per database block: 107b047 before them takes
  25.7 s, 894a4dd 7.9 minutes (46c272a doesn't import on its own), and every commit up to
  1.3.1 stays slow. It goes away with 0756037 in #234 (14.1 s), which factorizes each block
  once and keeps the solver. Before it, a block without a cached LU ran a fresh `spsolve`
  on every solve. Its parent 7eca883, which adds the solver module but doesn't call it
  yet, still takes 7.9 minutes.
- **bw_graph_tools 0.9's batched scoring (#46) makes traversal 1.6 to 6 times faster.**
  With PyPardiso and `max_calc=2`, ecoinvent goes from 623 to 383 ms and EXIOBASE from
  1.14 minutes to 11.3 s. With `max_calc=100`, ecoinvent goes from 19.1 to 8.53 s, and
  EXIOBASE from over asv's 15-minute limit to 2.25 minutes. 0.10 doesn't change it.
- **Without PyPardiso, traversal is hundreds of times slower.** At the ecoinvent size with
  `max_calc=2` it takes 4.6 minutes with SuperLU (3.95 from 0.9), against 0.62 s. It
  factorizes only once: a profile of 0.10 spends 234 of its 235 s in that one `splu`
  call and 1.4 s in the 10 solves. That call is bw2calc 2.5.0's `decompose_technosphere`,
  which factorizes A, the slow way round (see the bw2calc 3.0.0 bullet above). bw2calc
  3.1.0 factorizes Aᵀ there: a profile on 3.1.0 takes 27.8 s, 27.5 s of it in that one
  factorization, close to `LCA`'s 27.7 s with SuperLU.
  EXIOBASE finishes only from 0.9 (1.5 minutes), and only at
  `max_calc=2`: asv's 900 s limit covers a warm-up run too, and one run at `max_calc=100`
  alone takes 8.0 minutes.
  Before 0.9, ecoinvent at `max_calc=100` doesn't finish within the limit either, so the
  history has no SuperLU points there.
- **bw_processing #113 cuts building a matrix from 1,000 groups by 42%.** matrix_utils
  0.9 takes 724 ms on bw_processing 1.6 and 423 ms on #113, and every release from 0.5 shows
  about the same share. matrix_utils #48 saves another 4% (695 and 404 ms). Since 0.6,
  matrix_utils itself builds 11% slower at 1,000 groups (643 to 716 ms) and 22% slower at
  100.
- **bw_processing 1.6 iterates over 100,000 entries 24% faster** (309 to 234 ms). Adding
  1,000 resource groups takes 273 ms in every release, 120 times the 2.27 ms for 100: the
  cost grows with the square of the number of groups, which is what #113 removes.

## How the results stay reproducible

- [asv](https://asv.readthedocs.io) runs every release of a package on one fixed set of
  dependencies: those of its latest release, from before 2026-10-20, listed in
  `asv/<package>.stack.txt`. Only the package itself changes from one point in the history
  to the next, so a step in a graph is that package's change. One exception: bw2calc 3.0.0 and later
  need threadpoolctl, which its asv config installs beside the set, so that the older
  releases keep their history. They never import it.
- Each history starts at the oldest release that runs on that set. bw2data starts at 4.6,
  the first release on peewee 4, which older ones cannot import. bw_timex starts at 1.1.0,
  since 1.0.0 fails a check that bw_processing 1.6 added later. Every release of bw2calc,
  bw_processing, matrix_utils and bw_graph_tools runs.
- The solvers run on one thread, so a timing does not depend on how many cores were free.
- The noise floor, measured with `just noise` on a pinned benchmark machine, at the ecoinvent
  size, on a slot of 8 efficiency cores:
  - asv, six quick runs per arm: bw2calc's first score under PyPardiso spreads 0.0% with ASLR
    on and 0.1% with it off (interquartile range over the median). ASLR changes nothing
    measurable for the asv cells, so it stays on.
  - CodSpeed, three runs with ASLR off through the real `setarch -R` (see below): the
    traversal cases are 0.035% and 0.014% apart, against 0.7 to 1.1% with the old shim that
    left ASLR on.
  - bw2data's write takes about 12.7 s wall time and 11.7 s CPU time. In either arm, 1 or 2
    samples in 12 stall for 16 to 17 s off the CPU (3 of 36 samples over two nights), at the
    same time as the host writes its disk cache back (blocked processes in `vmstat`). asv's
    median does not move, but max/min is no usable spread for this cell.

  At the smoke size a case varies by up to 4% (median 0.9%, 10 runs), apart from cases of a
  few milliseconds. So a step of 5% or more at the ecoinvent size is a real change. Short
  cases need the CPU on its performance power profile (on Linux, `powerprofilesctl set
  performance`): under a power-saving one, an idle core starts slow and they vary up to
  five-fold. `just noise` also writes each sample's CPU time, wall time and involuntary
  context switches to `rounds.jsonl`; `scripts/noise_summary.py` says how to read them.
  On a GitHub-hosted `ubuntu-latest` runner (the `noise-hosted` workflow, bw2calc, 10 runs,
  smoke size) the same cases vary by 1 to 14%, median 4.0% (2 to 6% for cases of 50 ms or
  more). A hosted runner would catch a several-fold step such as bw2calc 3.0.0 factorizing A,
  but a change below about 15% can hide in its spread.
- CodSpeed's runner turns address randomization (ASLR) off with `setarch -R`. Docker's
  default seccomp profile refuses that, so the CodSpeed box runs under
  [`docker/seccomp-noaslr.json`](docker/seccomp-noaslr.json): Docker's default profile with one
  more rule, which allows only `personality(ADDR_NO_RANDOMIZE)` (`just seccomp-profile`
  rebuilds it).
- Each run records exactly what was installed (a `pylock.toml` lock file per environment)
  and an RO-Crate that names the code and settings that produced it.

## For developers

Run `uv sync`, then `just check` for lint, types and tests. These run no Brightway code.

- Benchmarks: [`benchmarks/`](benchmarks), configs and releases: [`asv/`](asv)
- Security: [SECURITY.md](.github/SECURITY.md)
- License: [LICENSE](LICENSE)
