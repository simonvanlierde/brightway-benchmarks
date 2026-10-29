# Findings

What the benchmark histories show so far, for people who use or maintain Brightway. Each
finding starts with the takeaway, then says what you can do about it, the numbers, and where
to see the graph or the upstream issue.

Unless a finding says otherwise, the numbers come from the
[benchmark history](https://simonvanlierde.com/brightway-benchmarks/), measured in October 2026
on the ecoinvent-sized synthetic database, one thread, on an efficiency core of an Intel
i9-14900KF. Every release of a package runs on the same fixed set of dependencies, so a step
in a history is that package's own change. [Method](method.md) explains the setup, the noise
floor and the database's limits: SuperLU times on it overstate real ecoinvent
([#54](https://github.com/simonvanlierde/brightway-benchmarks/issues/54)).

## bw2calc

The history holds all 15 bw2calc releases from 2.0 to 3.1.0. 2.1.1 has no git tag, so it shows
up under its commit, `a71ede78`.

### The solver sets the time for one score

**UMFPACK and PyPardiso give a score about 3 times faster than SciPy's SuperLU, and UMFPACK on
OpenBLAS about 10 times.**

What it means for you: install PyPardiso on x86_64, or scikit-umfpack from conda-forge
anywhere. With neither, bw2calc falls back to SuperLU.

| Solver | Time for one score with `LCA`, every release |
| --- | --- |
| SuperLU (SciPy) | 27.7 s |
| PyPardiso | 10.0 s |
| UMFPACK, scikit-umfpack built on reference BLAS | 9.05 s |
| UMFPACK, conda-forge's build on OpenBLAS | 2.63 s |
| UMFPACK, conda-forge's build on MKL's BLAS | 2.45 s |

Almost all of that time is the LU factorization: 98% of one score under PyPardiso, and 99% of
a Monte Carlo draw. Speeding up the rest of bw2calc can't help much. Reusing PARDISO's
reordering from one draw to the next saves about 2%.

Graph: [bw2calc, one score](https://simonvanlierde.com/brightway-benchmarks/bw2calc/index.html#bench_lca.SingleScore.time_first_score).

### No release changed the time for one score

**From 2.0 to 3.1.0, no bw2calc release changed `LCA`'s time for one score.** Across all
releases the times vary by 0.3% with every solver, so that is the smallest step the history
can show. Here "vary" is the interquartile range (the middle half of the points) relative to
the median. A point from a single round can stray by more: two outliers came back in line
when rerun with two rounds.

Graph: [bw2calc, one score](https://simonvanlierde.com/brightway-benchmarks/bw2calc/index.html#bench_lca.SingleScore.time_first_score).

### Keep the factorization for repeated solves

**A second functional unit on a solved system takes milliseconds, against seconds for the
first.** Warming up before the first score changes nothing: only a kept factorization helps.

What it means for you: to score many functional units on one technosphere, factorize once
with `lca.lci(factorize=True)`, then call `lca.redo_lci(demand)` for each one.

| Case | Time |
| --- | --- |
| First score, UMFPACK | 9.06 s |
| Second functional unit on the stored factorization, UMFPACK | 33.6 ms |
| First score in a fresh process, SuperLU | 19.2 s |
| First score after a warm-up solve, SuperLU | 19.1 s |
| First score, PyPardiso | 5.2 s |
| The same score with PyPardiso's factorization kept | 0.09 s |

The last four rows ran on a faster core than the history. The harness drops PyPardiso's
factorization before every timed first score, so the history times a real first score.

Graph: [bw2calc, second functional unit](https://simonvanlierde.com/brightway-benchmarks/bw2calc/index.html#bench_lca.NewDemand.time_redo_lci).

### UMFPACK's iterative refinement costs about two thirds of each repeated solve

**UMFPACK spends about two thirds of each solve on iterative refinement, and the score is the
same without it.** By default UMFPACK corrects each solution with extra solves. On the
ecoinvent matrix the score doesn't change without that correction.

What it means for you: nothing to do yet. bw2calc doesn't expose the setting
(`UMFPACK_IRSTEP`).
[brightway2-calc#184](https://github.com/brightway-lca/brightway2-calc/issues/184) proposes
turning it off, which would make repeated solves about 3 times faster on reference BLAS or
OpenBLAS.

One solve on the real ecoinvent 3.12 matrix:

| BLAS | Refinement on (default) | Refinement off |
| --- | --- | --- |
| Reference BLAS | 10.5 ms | 3.7 ms |
| conda-forge's OpenBLAS | 12.7 ms | 4.8 ms |
| MKL | 6.3 ms | 4.8 ms |

MKL already skips the refinement step, so it gains less. The `NewDemandRefinement` case times
both settings and checks the score against the reference either way.

### bw2calc 3.0.0 slowed `IterativeLCA` without PyPardiso, and 3.1.0 fixed it

**bw2calc 3.0.0 made `IterativeLCA` and `lci(factorize=True)` about 5 times slower with UMFPACK
and about 9 times slower with SuperLU. 3.1.0 is back to 2.5.0's times.**

What it means for you: if you run bw2calc 3.0.0 without PyPardiso, upgrade to 3.1.0.

| Case | Solver | 2.5.0 | 3.0.0 | 3.1.0 |
| --- | --- | --- | --- | --- |
| `IterativeLCA`, one score | UMFPACK | 9.04 s | 45.0 s | 9.05 s |
| `IterativeLCA`, one score | SuperLU | 27.7 s | about 4 minutes | 27.9 s |
| `LCA.lci(factorize=True)` | UMFPACK | | 45.0 s | 9.05 s |
| `LCA.lci(factorize=True)` | SuperLU | | 237 s | 27.7 s |

For SuperLU and UMFPACK, the transposed technosphere matrix Aᵀ factorizes several times faster
than A itself. `LCA`'s one score already took the fast way. In 3.0.0, `IterativeLCA` and
`lci(factorize=True)` call `factorized(matrix.tocsc())`, which factorizes A
([source](https://github.com/brightway-lca/brightway2-calc/blob/3.0.0/src/bw2calc/iterative_lca.py#L388)).
3.1.0 factorizes Aᵀ wherever it factorizes once and solves many times
([brightway2-calc#180](https://github.com/brightway-lca/brightway2-calc/pull/180)). asv's 600 s
limit covers a warm-up run too, so it cut off 3.0.0's SuperLU case, and the graph has no point
there.

Reported as [brightway2-calc#176](https://github.com/brightway-lca/brightway2-calc/issues/176).
Graph: [bw2calc, one score](https://simonvanlierde.com/brightway-benchmarks/bw2calc/index.html#bench_lca.SingleScore.time_first_score).

### `JacobiGMRESLCA` gives a score in 150 ms

**`JacobiGMRESLCA` (from 2.4.0) gives a score in 150 ms, with a relative error of 1.4e-9.**
That's on the synthetic matrix only. It hasn't been checked on ecoinvent.

Graph: [bw2calc, one score](https://simonvanlierde.com/brightway-benchmarks/bw2calc/index.html#bench_lca.SingleScore.time_first_score).

### The BLAS under scikit-umfpack sets UMFPACK's speed

**UMFPACK factorizes about 3 times faster on OpenBLAS or MKL than on reference BLAS. On
conda-forge's builds, a solve on a stored factorization is slower.**

What it means for you: install scikit-umfpack from conda-forge, which links OpenBLAS. If you
build it yourself, link OpenBLAS or MKL, not reference BLAS. If you mostly re-solve a stored
factorization, the PyPI build is a little faster there.

scikit-umfpack has no wheels on PyPI, so it builds against the system's SuiteSparse. In the
benchmark image that links Debian's reference BLAS, and the history's UMFPACK line uses it.
`bw2calc-conda` runs the same suite on conda-forge's builds of NumPy, SciPy, PyPardiso and
scikit-umfpack, on the same night and the same commits, two rounds each:

| Case | Solver | PyPI 3.1.0 | conda-forge 3.1.0 | PyPI 2.4.0 | conda-forge 2.4.0 |
| --- | --- | --- | --- | --- | --- |
| One score | SuperLU | 27.8 s | 27.7 s | 27.7 s | 27.6 s |
| One score | PyPardiso | 10.1 s | 10.0 s | 10.0 s | 10.0 s |
| One score | UMFPACK | 9.06 s | 2.63 s | 9.06 s | 2.63 s |
| Second functional unit | UMFPACK | 33.6 ms | 42.7 ms | 51.4 ms | 63.2 ms |
| `import bw2calc` | PyPardiso | 825 ms | 755 ms | 824 ms | 753 ms |

On conda-forge, UMFPACK's first score is about 3 times faster, and a solve on the stored
factorization is 23 to 27% slower. MKL's BLAS takes the first score to 2.45 s, and the second
functional unit still takes 42.7 ms. So the slower solve comes with conda-forge's builds, not
with the BLAS. PyPardiso (on conda-forge's MKL 2026.1.0) and SuperLU stay within 1%, and so
does peak memory. Importing bw2calc is 70 ms faster with PyPardiso and about 15 ms slower
without it. The scores are identical.

The real ecoinvent 3.12 matrix shows the same, if less (`scripts/solver_factorize.py`, same
core, two rounds):

| UMFPACK on | Factorize | One solve |
| --- | --- | --- |
| Reference BLAS (PyPI build) | 1.79 s | 16.5 ms |
| OpenBLAS (conda-forge) | 0.66 s | 24 ms |
| MKL (conda-forge) | 0.63 s | 24 ms |

Graph: [bw2calc-conda, one score](https://simonvanlierde.com/brightway-benchmarks/bw2calc-conda/index.html#bench_lca.SingleScore.time_first_score).

### Every new LCA object under PyPardiso searches for MKL again

**From 3.0.0, each LCA object under PyPardiso makes a fresh solver, which searches the Python
install for the MKL library.** That costs about 380 million more instructions per object than
2.5.0. 3.1.0 still shows it in wall time (checked on 2026-10-19).

What it means for you: if you create many small LCA objects, set `PYPARDISO_MKL_RT` to the
path of MKL's `mkl_rt` library. At the smoke size, that takes a first score from 37 to 2.7 ms.

The history keeps the search, since that is what users get. The fix belongs in PyPardiso:
[haasad/PyPardiso#91](https://github.com/haasad/PyPardiso/pull/91) finds the library once.
Tracked in [#56](https://github.com/simonvanlierde/brightway-benchmarks/issues/56).

### Two upstream crashes skip cases

Some releases crash on a case for a reason already reported upstream. The case is skipped with
the link, and runs again in the releases with the fix:

- `JacobiGMRESLCA` and `FastScoresOnlyMultiLCA` under PyPardiso free a factorization they never
  made ([brightway2-calc#157](https://github.com/brightway-lca/brightway2-calc/issues/157)).
- `IterativeLCA` passes `atol='legacy'` to SciPy's `cgs`, which the fixed SciPy rejects
  ([a comment on brightway2-calc#161](https://github.com/brightway-lca/brightway2-calc/pull/161#issuecomment-6140609983)).

## bw2data

The history holds bw2data from 4.6 to 4.8.

### bw2data 4.7 lost the faster database write

**bw2data 4.7 undid the 32% faster write that #268 had added two commits earlier. Reported as
[brightway2-data#306](https://github.com/brightway-lca/brightway2-data/issues/306).**

What it means for you: nothing to do yet.
[brightway2-data#308](https://github.com/brightway-lca/brightway2-data/pull/308) brings the
fast write back.

| bw2data | Writing an ecoinvent-sized database |
| --- | --- |
| 4.6.2 | 15.4 s |
| #268, raw SQLite `executemany` | 10.5 s |
| 4.7 | 15.3 s |
| 4.8 | 15.1 s |

The next commit after #268, #270 ("Fix unclosed sqlite3 connections"), took that code path
out again. 4.8 still writes with peewee's batches. Its small gain comes from #298, which skips
`VACUUM` when the database was empty. These times come from asv's `--interleave-rounds`, which
runs each round through all the commits. Runs that timed one commit after another drifted
between commits: one put 4.6.2 at 21.2 s.

The score after the write matches the reference in every release. The reference rounds
amounts to float32, as bw_processing stores them
([bw_processing#112](https://github.com/brightway-lca/bw_processing/issues/112)).

Graph: [bw2data, database write](https://simonvanlierde.com/brightway-benchmarks/bw2data/index.html#bench_write.DatabaseWrite.time_write).

## bw_timex

The history holds bw_timex from 1.1.0.

### bw_timex 1.3.0 made the time-explicit LCI about 19 times slower

**bw_timex 1.3.0 made the time-explicit LCI about 19 times slower. 1.3.2 fixed it, and 1.4.0
is faster again.**

What it means for you: use bw_timex 1.4.0 or later, and avoid 1.3.0 and 1.3.1.

| Time steps | 1.2.0 | 1.3.0 | 1.3.2 | 1.4.0 |
| --- | --- | --- | --- | --- |
| 5 | 25.9 s | 8.4 minutes | 13.4 s | 3.3 s |
| 20 | 34.1 s | 7.9 minutes | 19.3 s | 9.3 s |

1.3.0 solves the background unit LCIs per database block, and a block without a cached LU ran
a fresh `spsolve` on every solve. The slowdown came in with commits 46c272a and 894a4dd.
[bw_timex#234](https://github.com/brightway-lca/bw_timex/pull/234), in 1.3.2, factorizes each
block once and keeps the solver. 1.4.0 solves the technosphere blocks by a Neumann series.

Graph: [bw_timex, time-explicit LCI](https://simonvanlierde.com/brightway-benchmarks/bw_timex/index.html#bench_timex.TimelineLCI.time_lci).

### bw_timex's tests fail under pytest 9.2.0

**Three of bw_timex's explicit product-modelling tests fail under pytest 9.2.0.** The compat
`suites` column found it. Reported as
[bw_timex#247](https://github.com/brightway-lca/bw_timex/issues/247).

## bw_graph_tools

The history holds every bw_graph_tools release, at the ecoinvent and EXIOBASE sizes.

### bw_graph_tools 0.9 made traversal 1.6 to 6 times faster

**bw_graph_tools 0.9's batched scoring (#46) makes traversal 1.6 to 6 times faster.** 0.10
doesn't change it.

What it means for you: use 0.9 or later.

With PyPardiso:

| Database | `max_calc` | Before 0.9 | From 0.9 |
| --- | --- | --- | --- |
| ecoinvent | 2 | 623 ms | 383 ms |
| ecoinvent | 100 | 19.1 s | 8.53 s |
| EXIOBASE | 2 | 1.14 minutes | 11.3 s |
| EXIOBASE | 100 | over asv's 15-minute limit | 2.25 minutes |

Graph: [bw_graph_tools, traversal](https://simonvanlierde.com/brightway-benchmarks/bw_graph_tools/index.html#bench_traversal.Traversal.time_traverse).

### Without PyPardiso, traversal is hundreds of times slower

**Without PyPardiso, a traversal of the ecoinvent-sized database takes minutes instead of
under a second, and nearly all of it is one factorization.**

What it means for you: traverse with PyPardiso. Without it, use bw2calc 3.1.0 or later, which
cuts that factorization from minutes to under 30 s.

At the ecoinvent size with `max_calc=2`, a traversal takes 4.6 minutes with SuperLU (3.95
minutes from 0.9), against 0.62 s with PyPardiso. A profile of 0.10 spends 234 of its 235 s in
one `splu` call, and 1.4 s in the 10 solves. That call is bw2calc 2.5.0's
`decompose_technosphere`, which factorizes A, not Aᵀ (see
[the bw2calc 3.0.0 finding](#bw2calc-300-slowed-iterativelca-without-pypardiso-and-310-fixed-it)).
bw2calc 3.1.0 factorizes Aᵀ there: on 3.1.0 the same profile takes 27.8 s, 27.5 s of it in
that factorization, close to `LCA`'s 27.7 s with SuperLU.

asv's 900 s limit covers a warm-up run too. So with SuperLU, EXIOBASE finishes only from 0.9
(1.5 minutes), and only at `max_calc=2`: one run at `max_calc=100` alone takes 8.0 minutes.
Before 0.9, ecoinvent at `max_calc=100` doesn't finish within the limit either, so the history
has no SuperLU points there.

[bw_graph_tools#58](https://github.com/brightway-lca/bw_graph_tools/issues/58) proposes
getting all unit scores from one transposed solve that reuses the LCA's factorization.

Graph: [bw_graph_tools, traversal](https://simonvanlierde.com/brightway-benchmarks/bw_graph_tools/index.html#bench_traversal.Traversal.time_traverse).

### A bw_graph_tools test fails with PyPardiso

**bw_graph_tools 0.10's `test_only_one_node_error_message` fails when PyPardiso is installed.**
The compat `suites` column found it.

## bw_processing and matrix_utils

The history holds every release of both.

### Adding resource groups grows with the square of their number

**The time to add resource groups to a datapackage grows with the square of their number.
[bw_processing#113](https://github.com/brightway-lca/bw_processing/pull/113) removes that, and
cuts building a matrix from 1,000 groups by 42%.**

What it means for you: nothing to do until a bw_processing release has #113.

| Case | Time |
| --- | --- |
| Add 100 resource groups, every bw_processing release | 2.27 ms |
| Add 1,000 resource groups, every bw_processing release | 273 ms |
| matrix_utils 0.9 builds from 1,000 groups, bw_processing 1.6 | 724 ms |
| The same on bw_processing#113 | 423 ms |
| The same with [matrix_utils#48](https://github.com/brightway-lca/matrix_utils/pull/48), on 1.6 and on #113 | 695 ms and 404 ms |

Ten times the groups take 120 times as long. Every matrix_utils release from 0.5 shows about
the same gain from #113. Since 0.6, matrix_utils itself builds 11% slower at 1,000 groups (643
to 716 ms), and 22% slower at 100.

Graphs: [bw_processing, resource groups](https://simonvanlierde.com/brightway-benchmarks/bw_processing/index.html#bench_datapackage.Groups.time_groups),
[matrix_utils, matrix build](https://simonvanlierde.com/brightway-benchmarks/matrix_utils/index.html#bench_mapped_matrix.MappedMatrixBuild.time_mapped_matrix).

### bw_processing 1.6 iterates over entries 24% faster

**bw_processing 1.6 iterates over 100,000 entries 24% faster**, from 309 to 234 ms.

Graph: [bw_processing, iterating entries](https://simonvanlierde.com/brightway-benchmarks/bw_processing/index.html#bench_datapackage.EntriesPath.time_vars_iterator).

### Amounts are stored as float32

**bw_processing stores processed exchange amounts as float32, which moves scores by about
1e-7.** Reported as
[bw_processing#112](https://github.com/brightway-lca/bw_processing/issues/112). bw2data's score
check uses a reference with the same float32 amounts.

## bw2io

### bw2io's exporter tests fail with bw2data 4.8

**Five of bw2io 0.9.17's CSV and Excel exporter tests fail with bw2data 4.8.** The compat
`suites` column found it. Reported as
[brightway2-io#354](https://github.com/brightway-lca/brightway2-io/issues/354).

## Across packages

### Twelve declared dependency floors are too low

**Twelve lower bounds that Brightway packages declare are too low on Python 3.12: the oldest
release they allow fails.** They are in bw2parameters, bw_processing, bw2data, bw2calc and
bw_timex. The compat `floors` column finds them.

What it means for you: if your environment holds an old release of one of these dependencies,
raise it to the version that [`scripts/compat.sh`](../scripts/compat.sh) lists. That file
names each floor, the oldest release that works, and the package that declares it.

The rows marked "Floors" in the table below report them upstream.

### conda-forge gets releases late

**conda-forge gets a Brightway release only once its feedstock merges the update.** bw2calc
stayed at 2.4.0 there until 3.1.0 landed on 2026-10-18. bw_graph_tools and bw_timex are not
on conda-forge yet.

What it means for you: check the `conda-forge` row of the site's
[works together today](https://simonvanlierde.com/brightway-benchmarks/#works-together) table
before you install from conda-forge.

## Upstream issues and pull requests

Every issue and pull request this work filed upstream, with its status on 2026-10-29.

| Package | Issue or pull request | Finding | Status |
| --- | --- | --- | --- |
| bw2calc | [brightway2-calc#176](https://github.com/brightway-lca/brightway2-calc/issues/176) | 3.0.0's `IterativeLCA` factorizes A without PyPardiso | closed, fixed by #180 |
| bw2calc | [brightway2-calc#184](https://github.com/brightway-lca/brightway2-calc/issues/184) | A `solvers` extra with KLU; UMFPACK's refinement | open |
| bw2calc | [brightway2-calc#185](https://github.com/brightway-lca/brightway2-calc/pull/185) | Floors | open |
| bw2data | [brightway2-data#306](https://github.com/brightway-lca/brightway2-data/issues/306) | 4.7 lost the faster write | open |
| bw2data | [brightway2-data#308](https://github.com/brightway-lca/brightway2-data/pull/308) | Brings the faster write back | open |
| bw2data | [brightway2-data#309](https://github.com/brightway-lca/brightway2-data/pull/309) | Floors | open |
| bw2io | [brightway2-io#354](https://github.com/brightway-lca/brightway2-io/issues/354) | Exporter tests fail with bw2data 4.8 | open |
| bw2parameters | [brightway2-parameters#15](https://github.com/brightway-lca/brightway2-parameters/issues/15) | Floors: astunparse | open |
| bw2parameters | [brightway2-parameters#16](https://github.com/brightway-lca/brightway2-parameters/pull/16) | Floors | open |
| bw_processing | [bw_processing#113](https://github.com/brightway-lca/bw_processing/pull/113) | Resource groups grow with the square of their number | open |
| bw_processing | [bw_processing#115](https://github.com/brightway-lca/bw_processing/pull/115) | Floors: fsspec | open |
| matrix_utils | [matrix_utils#48](https://github.com/brightway-lca/matrix_utils/pull/48) | Building a matrix from many groups | open |
| bw_graph_tools | [bw_graph_tools#55](https://github.com/brightway-lca/bw_graph_tools/pull/55) | All unit scores from one transposed solve | closed |
| bw_graph_tools | [bw_graph_tools#58](https://github.com/brightway-lca/bw_graph_tools/issues/58) | The same, reusing the LCA's factorization | open |
| bw_timex | [bw_timex#244](https://github.com/brightway-lca/bw_timex/pull/244) | The timeline's matrix entries as one vector per matrix | merged |
| bw_timex | [bw_timex#246](https://github.com/brightway-lca/bw_timex/pull/246) | Floors | open |
| bw_timex | [bw_timex#247](https://github.com/brightway-lca/bw_timex/issues/247) | Tests fail under pytest 9.2 | open |
| brightway25 | [brightway25#13](https://github.com/brightway-lca/brightway25/pull/13) | conda recipe: drop the pin to NumPy below 2 | open |
| PyPardiso | [haasad/PyPardiso#91](https://github.com/haasad/PyPardiso/pull/91) | The MKL search on every new solver | open |
| conda-forge | [conda-forge/staged-recipes#35306](https://github.com/conda-forge/staged-recipes/pull/35306) | Adds bw_graph_tools to conda-forge | open |
