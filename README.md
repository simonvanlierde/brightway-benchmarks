# brightway-benchmarks

[![python](https://github.com/simonvanlierde/brightway-benchmarks/actions/workflows/python.yml/badge.svg)](https://github.com/simonvanlierde/brightway-benchmarks/actions/workflows/python.yml)
[![license](https://img.shields.io/badge/license-BSD--3--Clause-blue.svg)](LICENSE)

How fast is [Brightway](https://docs.brightway.dev), and does it still give the right answer?
This repository times the calculations an LCA practitioner runs every day, across
Brightway's released versions: an LCI and LCIA, many functional units at once, Monte Carlo.
It also checks every result against an independent reference score. A release that makes a
calculation slower, or quietly changes a score, shows up here.

No licensed data is used. The benchmarks run on synthetic databases that copy the structure
of ecoinvent, so anyone can rerun them and the results can be published.

## What is measured

| Package | What is timed, in LCA terms |
| --- | --- |
| bw2calc | One score (build the matrices, solve, characterize); a second functional unit on a solved system; many functional units against three impact categories; Monte Carlo draws |
| bw2data | Writing a database, up to the size of ecoinvent |
| bw_processing, matrix_utils | Building datapackages and matrices from many resource groups |
| bw_graph_tools | Supply-chain graph traversal, small and large |
| bw_timex | The time-explicit LCI as the timeline grows |

bw2calc runs each case with the direct solvers (PyPardiso, UMFPACK, SuperLU) and with its
iterative solvers.

Each benchmark checks its score next to the timing, against a reference that uses no
Brightway code at all. So a fast but wrong release fails instead of looking good. Only the
bw_processing cases that build datapackages from entries have nothing to check.

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
share more of their consumers. [TODO.md](TODO.md) tracks the work on it.

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
just solver-lci klu ecoinvent     # bw2calc 3.0.0's own lci() with one solver, KLU here
just codspeed bw2calc pypardiso  # one suite under CodSpeed's CPU simulation (instruction counts)
```

Every benchmark runs on the 200-product `smoke` database unless you pick others. For
example, `BWBENCH_SIZES=ecoinvent just bench bw2calc` times the ecoinvent-sized one.
`BWBENCH_SIZES` sets the size for most cases, and three cases have their own variable:
`BWBENCH_MC_SIZES` (Monte Carlo), `BWBENCH_WRITE_SIZES` (bw2data) and `BWBENCH_TIMEX_SIZES`
(bw_timex).
`BWBENCH_SOLVERS` picks the solver environments of bw2calc and bw_graph_tools: `superlu`,
`pypardiso` and `umfpack`, all three by default. PyPardiso needs Intel's MKL, so off x86_64
(an Apple Silicon Mac, say) the default is `superlu,umfpack`. A full-size bw2calc run takes
about 24 minutes with the SuperLU environment and 6 with `BWBENCH_SOLVERS=pypardiso`.
asv times each case in 2 rounds by default; `BWBENCH_ROUNDS=1` halves a full-size run.
Each result is checked once per parameter set, not after every sample.

When a package publishes a new release, `just stack` and `just stack-check` move its fixed
set of dependencies (below) forward; the steps are in the [justfile](justfile).

## Results so far

The history pages are at <https://simonvanlierde.github.io/brightway-benchmarks/>.
So far they hold all 14 bw2calc releases from 2.0 to 3.0.0 on the ecoinvent-sized database.
2.1.1 has no git tag, so it shows up under its commit, `a71ede78`.
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
- **bw2calc 3.0.0 made `IterativeLCA` much slower without PyPardiso.** One score takes
  45.0 s with UMFPACK, against 9.04 s in 2.5.0, and about 4 minutes with SuperLU, against
  27.7 s. asv's 600 s limit covers a warm-up run too, so it cut the SuperLU case off.
  `LCA` didn't change. Without PyPardiso, 3.0.0's `IterativeLCA` calls `factorized(matrix.tocsc())`, which factorizes A, the slow way
  round for both solvers ([`iterative_lca.py`](https://github.com/brightway-lca/brightway2-calc/blob/3.0.0/src/bw2calc/iterative_lca.py#L388)).
  `LCA.lci(factorize=True)` makes the same call and takes 45.0 s with UMFPACK, the same
  time as `IterativeLCA`, and 237 s with SuperLU.
- **The UMFPACK line uses reference BLAS.** scikit-umfpack has no wheels, so it builds
  against the SuiteSparse in the benchmark image, which links Debian's reference BLAS.
  With OpenBLAS in its place, one score takes 2.6 s instead of 9.0 s. scikit-umfpack from
  conda-forge comes with an optimized BLAS, so for those users this line probably
  overstates the time by about 3.5x.

### The other packages

Every release of bw_processing, matrix_utils and bw_graph_tools, bw2data from 4.6 and
bw_timex from 1.1.0, on the same core. bw_graph_tools ran at the ecoinvent and EXIOBASE
sizes, the others at the ecoinvent size.

- **bw2data 4.7 lost the faster database write it gained two commits earlier.** Writing
  the database takes 15.4 s in 4.6 and 4.6.2. #268 (raw SQLite `executemany`) brings it to
  10.5 s, and the next commit, #270 ("Fix unclosed sqlite3 connections"), takes that code
  path out again, so 4.7 and `main` write in 15.6 s. From #268 on, single writes also
  scatter (a quarter of the five rounds over 26 s, against 15.4 to 15.5 s in 4.6), which
  needs more rounds before it means anything. The score after the write is off by 5.7e-8
  in every release.
- **bw_timex 1.3.0 made the time-explicit LCI about 19 times slower.** With 5 time steps
  it takes 25.9 s in 1.2.0, 8.4 minutes in 1.3.0, 13.4 s in 1.3.2 and 3.3 s in 1.4.0 (which
  solves technosphere blocks by a Neumann series); with 20 steps 34.1 s, 7.9 minutes,
  19.3 s and 9.3 s. 1.3.2 replaces PARDISO thrashing in grouped block solves with a
  per-block LU, which is probably the fix, but I haven't bisected it.
- **bw_graph_tools 0.9's batched scoring (#46) makes traversal 1.6 to 6 times faster.**
  With PyPardiso and `max_calc=2`, ecoinvent goes from 623 to 383 ms and EXIOBASE from
  1.14 minutes to 11.3 s. With `max_calc=100`, ecoinvent goes from 19.1 to 8.53 s, and
  EXIOBASE from over asv's 15-minute limit to 2.25 minutes. 0.10 doesn't change it.
- **Without PyPardiso, traversal is hundreds of times slower.** At the ecoinvent size with
  `max_calc=2` it takes 4.6 minutes with SuperLU (3.95 from 0.9), against 0.62 s. That's 9
  calculations, close to nine of SuperLU's 27.7 s factorizations, so each calculation
  probably factorizes again. EXIOBASE finishes only from 0.9 (1.5 minutes), and only at
  `max_calc=2`: asv's 900 s limit covers a warm-up run too, and one run at `max_calc=100`
  alone takes 8.0 minutes.
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
  dependencies: those of its latest release, from before 2026-10-06, listed in
  `asv/<package>.stack.txt`. Only the package itself changes from one point in the history
  to the next, so a step in a graph is that package's change. One exception: bw2calc 3.0.0
  needs threadpoolctl, which its asv config installs beside the set, so that the older
  releases keep their history. They never import it.
- Each history starts at the oldest release that runs on that set. bw2data starts at 4.6,
  the first release on peewee 4, which older ones cannot import. bw_timex starts at 1.1.0,
  since 1.0.0 fails a check that bw_processing 1.6 added later. Every release of bw2calc,
  bw_processing, matrix_utils and bw_graph_tools runs.
- The solvers run on one thread, so a timing does not depend on how many cores were free.
- Between runs, a case's time varies by at most 1% at the ecoinvent size (median 0.1%,
  PyPardiso, 5 runs) and by up to 4% at the smoke size (median 0.9%, 10 runs), apart from
  cases of a few milliseconds (`just noise`). So a step of 5% or more at the ecoinvent size
  is a real change. Short cases need the CPU on its performance power profile (on Linux,
  `powerprofilesctl set performance`): under a power-saving one, an idle core starts slow
  and they vary up to five-fold.
- Each run records exactly what was installed (a `pylock.toml` lock file per environment)
  and an RO-Crate that names the code and settings that produced it.

## For developers

Run `uv sync`, then `just check` for lint, types and tests. These run no Brightway code.

- Benchmarks: [`benchmarks/`](benchmarks), configs and releases: [`asv/`](asv)
- Security: [SECURITY.md](.github/SECURITY.md)
- License: [LICENSE](LICENSE)
