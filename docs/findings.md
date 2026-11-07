# Findings

Unless a finding says otherwise, the numbers come from the
[benchmark history](https://simonvanlierde.com/brightway-benchmarks/), measured in October 2026
on the ecoinvent-sized synthetic database, one thread, on an efficiency core of an Intel
i9-14900KF. Every release runs on the same fixed dependencies, so a step in a history is that
package's own change ([method](method.md)). Direct-solver times on the synthetic database
overstate real ecoinvent: a SuperLU score takes 27.7 s against a 3.66 s factorization of the real
matrix, and UMFPACK on reference BLAS 9.05 s against 1.79 s, because the profile's factors fill
about three times as much ([#54](https://github.com/simonvanlierde/brightway-benchmarks/issues/54)).

The pinned [#85](https://github.com/simonvanlierde/brightway-benchmarks/issues/85) lists every
upstream issue with its current state.

## bw2calc

### The solver sets the time for one score

**UMFPACK and PyPardiso give a score about 3 times faster than SciPy's SuperLU, and UMFPACK on
OpenBLAS about 10 times.**

[What to do](faster.md).

| Solver | One score with `LCA`, every release |
| --- | --- |
| SuperLU (SciPy) | 27.7 s |
| PyPardiso | 10.0 s |
| UMFPACK, scikit-umfpack built on reference BLAS | 9.05 s |
| UMFPACK, conda-forge's build on OpenBLAS | 2.63 s |
| UMFPACK, conda-forge's build on MKL's BLAS | 2.45 s |

The LU factorization is 98% of one score under PyPardiso, and 99% of a Monte Carlo draw. No
release from 2.0 to 3.1.0 changed these times. `JacobiGMRESLCA` (from 2.4.0) gives a
score in 150 ms, with a relative error of 1.4e-9, on the synthetic matrix only.

Graph: [bw2calc, one score](https://simonvanlierde.com/brightway-benchmarks/?page=explorer&group=bw2calc&bench=bench_lca.SingleScore.time_first_score).
Rerun: [`bench_lca.SingleScore`](../benchmarks/bench_bw2calc/bench_lca.py).

### Energy per first score

**PyPardiso and UMFPACK used about 180 J above idle per score, against 483 J for SuperLU.**

A quiet run on 7 November 2026 measured CPU package energy with Intel RAPL, using bw2calc
3.1.0, Python 3.12, one thread on the same efficiency-core slot, and generator v4's
ecoinvent-sized profile. The fill caveat above applies. A five-minute baseline measured
9.19 W; each sample subtracts that power times its own elapsed time.

| Solver | Median package J / score | Median J above idle | Above-idle range, 3 samples |
| --- | --- | --- | --- |
| SuperLU (SciPy) | 738 | 483 | 480–490 |
| PyPardiso | 273 | 180 | 177–184 |
| UMFPACK, reference BLAS | 263 | 179 | 167–210 |

The UMFPACK and PyPardiso energy ranges overlap. Three samples do not establish which uses
less energy. Each reading covers one first score, with setup and verification outside the
measured span. RAPL covers the CPU package, including other processes; it does not measure
whole-machine power. [Measurement and idle subtraction](running.md#energy-per-operation).

### Keep the factorization for repeated solves

**A second functional unit on a solved system takes milliseconds, against seconds for the
first.** A warm-up solve doesn't help.

[What to do](faster.md).

With UMFPACK, a second functional unit on the stored factorization takes 33.6 ms, against
9.06 s for the first score. On a faster core, PyPardiso's kept factorization takes a score from
5.2 to 0.09 s, and SuperLU's first score takes 19.1 s after a warm-up solve, against 19.2 s
without.

Graph: [bw2calc, second functional unit](https://simonvanlierde.com/brightway-benchmarks/?page=explorer&group=bw2calc&bench=bench_lca.NewDemand.time_redo_lci).
Rerun: [`bench_lca.NewDemand`](../benchmarks/bench_bw2calc/bench_lca.py).

### UMFPACK's speed depends on its BLAS and its refinement step

**UMFPACK factorizes about 3 times faster on OpenBLAS or MKL than on reference BLAS. On
reference BLAS and OpenBLAS, about two thirds of each repeated solve is iterative refinement,
which doesn't change the score.**

bw2calc can't turn refinement off yet
([brightway2-calc#186](https://github.com/brightway-lca/brightway2-calc/pull/186) does). [What to do](faster.md).

The history builds scikit-umfpack, which has no PyPI wheels, on Debian's reference BLAS.
`bw2calc-conda` runs the suite on conda-forge's builds instead. There, on bw2calc 2.4.0 and
3.1.0 alike, UMFPACK's first score drops from 9.06 to 2.63 s, but a second functional unit is
23 to 27% slower (42.7 against 33.6 ms on 3.1.0), on MKL's BLAS too. So the slower solve comes
with conda-forge's builds, not the BLAS. Other solvers stay within 1%, and scores match.

On the real ecoinvent 3.12 matrix:

| UMFPACK on | Factorize | `lu_solver` solve | Aᵀx = b, refinement on | Aᵀx = b, refinement off |
| --- | --- | --- | --- | --- |
| Reference BLAS (PyPI build) | 1.79 s | 16.5 ms | 10.5 ms | 3.7 ms |
| OpenBLAS (conda-forge) | 0.66 s | 24 ms | 12.7 ms | 4.8 ms |
| MKL (conda-forge) | 0.63 s | 24 ms | 6.3 ms | 4.8 ms |

The two pairs of columns time different solves, so don't compare across them. The first pair
comes from [`scripts/solver_factorize.py`](../scripts/solver_factorize.py) through bw2calc's
`lu_solver`. The second times UMFPACK's direct solve of Aᵀx = b. MKL takes no refinement step.
With refinement off, conda-forge's UMFPACK is about 30% slower per solve than the PyPI build.

Every direct solver on the same matrix, through the same script, with bw2calc 3.1.0, SciPy
1.18.1, scikit-umfpack 0.4.2 from PyPI, PyPardiso 0.4.7 and pyklu 0.2.0, on one thread and
the same efficiency cores. The two conda-forge rows repeat the table above.

| Solver | Factorize |
| --- | --- |
| SuperLU (SciPy) | 3.66 s |
| UMFPACK, PyPI build on reference BLAS | 1.78 s |
| PyPardiso | 1.48 s |
| KLU through pyklu, which bw2calc can't pick | 1.31 s |
| UMFPACK, conda-forge's build on OpenBLAS | 0.66 s |
| UMFPACK, conda-forge's build on MKL's BLAS | 0.63 s |

The matrix has 26,533 rows and 338,195 nonzeros. A solve on the factors takes 5 to 24 ms, so
factorizing is 96 to over 99% of the solver's time. SuperLU's whole `spsolve`, the call
`LCA.lci()` makes, takes 3.66 s. So SuperLU takes about 5.5 times as long as conda-forge's
UMFPACK, against about 10 times on the synthetic database. On a performance core, each time is
1.7 to 2 times shorter, in the same order (conda-forge's builds weren't run there).

Graph: [bw2calc-conda, one score](https://simonvanlierde.com/brightway-benchmarks/?page=explorer&group=bw2calc-conda&bench=bench_lca.SingleScore.time_first_score).
Rerun: [`bench_lca.NewDemandRefinement`](../benchmarks/bench_bw2calc/bench_lca.py).

### bw2calc 3.0.0 slowed `IterativeLCA` without PyPardiso, and 3.1.0 fixed it

**bw2calc 3.0.0 made `IterativeLCA` about 5 times slower with UMFPACK and about 9 times slower
with SuperLU. 3.1.0 is back to 2.5.0's times, and also makes `lci(factorize=True)` fast for
the first time.**

| Case | Solver | 2.5.0 | 3.0.0 | 3.1.0 |
| --- | --- | --- | --- | --- |
| `IterativeLCA`, one score | UMFPACK | 9.04 s | 45.0 s | 9.05 s |
| `IterativeLCA`, one score | SuperLU | 27.7 s | about 4 minutes | 27.9 s |
| `LCA.lci(factorize=True)` | UMFPACK | | 45.0 s | 9.05 s |
| `LCA.lci(factorize=True)` | SuperLU | | 237 s | 27.7 s |

SuperLU and UMFPACK factorize Aᵀ several times faster than A. `lci(factorize=True)` factorized
A in 2.5.0 and 3.0.0, as did 3.0.0's `IterativeLCA`. 3.1.0 factorizes Aᵀ
([brightway2-calc#180](https://github.com/brightway-lca/brightway2-calc/pull/180)). Reported as
[brightway2-calc#176](https://github.com/brightway-lca/brightway2-calc/issues/176).

Rerun: [`bench_lca.SingleScore`](../benchmarks/bench_bw2calc/bench_lca.py), and
`just solver-lci umfpack ecoinvent 3.0.0` for `lci(factorize=True)`.

### bw2calc 3.0.0 doubled JacobiGMRESLCA's Monte Carlo time

**bw2calc 3.0.0 made `JacobiGMRESLCA` about 2.2 times slower in Monte Carlo, with every solver.
3.1.0 has not fixed it.**

What it means for you: for Monte Carlo with `JacobiGMRESLCA`, 2.5.0 is about twice as fast.
Nothing else changes.

The case is ten draws after the first score, on the ecoinvent-sized synthetic database. The
class never factorizes, so the solver makes no difference.

| bw2calc | Solvers | `JacobiGMRESLCA`, 10 draws |
| --- | --- | --- |
| 2.5.0 | KLU, UMFPACK, UMFPACK on Aᵀ, SuperLU | 0.324 s (0.323 to 0.325 s) |
| 3.0.0 | the same, and PyPardiso | 0.700 s (0.696 to 0.708 s) |
| 2.4.0, conda-forge builds | UMFPACK, UMFPACK on MKL, SuperLU | 0.330 s |
| 3.1.0, conda-forge builds | the same | 0.702 s |

The slowdown starts with the commit that made `JacobiGMRESLCA` a subclass of `IterativeLCA`
([brightway2-calc#161](https://github.com/brightway-lca/brightway2-calc/pull/161)). A single
score with `JacobiGMRESLCA` did not change.

Graph: [bw2calc, Monte Carlo](https://simonvanlierde.com/brightway-benchmarks/?page=explorer&group=bw2calc&bench=bench_lca.MonteCarlo.time_iterations).
Rerun: [`bench_lca.MonteCarlo`](../benchmarks/bench_bw2calc/bench_lca.py).

### cuDSS refactorizes real ecoinvent in 37 ms, but that isn't a Monte Carlo draw yet

**On real ecoinvent 3.12 cut-off, NVIDIA's cuDSS factorizes on the GPU in about 0.25 s and
repeats the numeric factorization in 37 to 38 ms, about 6 times faster than PARDISO on eight
threads.** It's a solver probe: the repeat reuses the same values and sparsity pattern.

What it means for you: nothing yet. bw2calc can't use cuDSS, and these times don't include
sampling, rebuilding the matrices, or the inventory and impact scores of a real draw.

Two rounds at each CPU thread count ran on the performance cores of an Intel i9-14900KF with an
NVIDIA RTX 4090. Each round takes the median of three factorizations and five solves; the table
gives the range over the two rounds. GPU times include the transfers to and from the host. The
CUDA context and library warm-up happen before timing.

| Solver | CPU threads | First factorization | Repeated numeric factorization | Solve |
| --- | --- | --- | --- | --- |
| SuperLU | 1 | 2.45 to 2.66 s | Not measured | 5.50 to 5.60 ms |
| UMFPACK, reference BLAS | 1 | 1.07 to 1.08 s | Not measured | 9.70 ms |
| KLU | 1 | 0.766 to 0.833 s | Not measured | 2.90 to 5.40 ms |
| PARDISO | 1 | 0.779 to 0.791 s | 0.610 to 0.615 s | 9.70 to 10.4 ms |
| PARDISO | 8 | 0.291 to 0.392 s | 0.211 to 0.248 s | 7.70 to 9.50 ms |
| cuDSS | 1 or 8 | 0.250 to 0.257 s | 37.0 to 38.0 ms | 1.00 to 1.10 ms |

The scores agree with UMFPACK to a relative difference of at most 4e-12, checked with a random
positive characterization row. With changing values (`--cudss-updates`: three row-scaled
updates, same sparsity), cuDSS still refactorizes in 34 to 37 ms without a new analysis, and the
solutions stay within a relative difference of 4e-10 of SuperLU's.

Before anyone claims this for Monte Carlo, a GPU backend needs real LCA draws, changed sparsity
and resource cleanup tested. It's the case for letting callers choose the solver in bw2calc
([brightway2-calc#184](https://github.com/brightway-lca/brightway2-calc/issues/184)).

Rerun: [`scripts/solver_factorize.py --pardiso --cudss`](../scripts/solver_factorize.py), with
your own licensed ecoinvent release. Its module docstring gives the container command and the
pinned GPU packages.

### Every new LCA object under PyPardiso searches for MKL again

**From 3.0.0, each LCA object under PyPardiso makes a fresh solver, which searches the Python
install for the MKL library.** 3.1.0 still does.

[What to do](faster.md).
[haasad/PyPardiso#91](https://github.com/haasad/PyPardiso/pull/91) would find the library once
([#56](https://github.com/simonvanlierde/brightway-benchmarks/issues/56)).

Rerun: `just codspeed bw2calc bw2calc==3.0.0 pypardiso`.

### Two upstream crashes skip cases

`JacobiGMRESLCA` and `FastScoresOnlyMultiLCA` under PyPardiso free a factorization they never
made ([brightway2-calc#157](https://github.com/brightway-lca/brightway2-calc/issues/157)).
`IterativeLCA` passes `atol='legacy'` to SciPy's `cgs`, which the pinned SciPy rejects
([brightway2-calc#161](https://github.com/brightway-lca/brightway2-calc/pull/161#issuecomment-6140609983)).
[`skip_known_crash`](../benchmarks/bench_bw2calc/bench_lca.py) lists both.

## bw2data

### bw2data 4.7 lost the faster database write

**bw2data 4.7 undid #268, which had cut the write time by 32% two commits earlier.**

What it means for you: nothing yet.
[brightway2-data#308](https://github.com/brightway-lca/brightway2-data/pull/308) brings it back
([brightway2-data#306](https://github.com/brightway-lca/brightway2-data/issues/306)).

Writing an ecoinvent-sized database takes 15.3 s on 4.6.2 and 4.7, and 15.1 s on 4.8. #268's
raw SQLite `executemany` took 10.4 s, and #270, the next commit, 15.4 s. These times come from
asv's `--interleave-rounds`.

Graph: [bw2data, database write](https://simonvanlierde.com/brightway-benchmarks/?page=explorer&group=bw2data&bench=bench_write.DatabaseWrite.time_write).
Rerun: [`bench_write.DatabaseWrite`](../benchmarks/bench_bw2data/bench_write.py).

## bw_timex

### bw_timex 1.3.0 made the time-explicit LCI about 19 times slower

**bw_timex 1.3.0 made the time-explicit LCI about 19 times slower. 1.3.2 fixed it, and 1.4.0
is faster again.**

What it means for you: use bw_timex 1.4.0 or later, and avoid 1.3.0 and 1.3.1.

| Time steps | 1.2.0 | 1.3.0 | 1.3.2 | 1.4.0 |
| --- | --- | --- | --- | --- |
| 5 | 25.9 s | 8.4 minutes | 13.4 s | 3.3 s |
| 20 | 34.1 s | 7.9 minutes | 19.3 s | 9.3 s |

In 1.3.0, a database block without a cached LU was factorized again on every solve.
[bw_timex#234](https://github.com/brightway-lca/bw_timex/pull/234), in 1.3.2, factorizes each
block once.

Graph: [bw_timex, time-explicit LCI](https://simonvanlierde.com/brightway-benchmarks/?page=explorer&group=bw_timex&bench=bench_timex.TimelineLCI.time_lci).
Rerun: [`bench_timex.TimelineLCI`](../benchmarks/bench_bw_timex/bench_timex.py).

## bw_graph_tools

### bw_graph_tools 0.9 made traversal 1.6 to 6 times faster

**bw_graph_tools 0.9's batched scoring makes traversal 1.6 to 6 times faster.** Use 0.9 or
later.

| Database, with PyPardiso | `max_calc` | Before 0.9 | From 0.9 |
| --- | --- | --- | --- |
| ecoinvent | 2 | 623 ms | 383 ms |
| ecoinvent | 100 | 19.1 s | 8.53 s |
| EXIOBASE | 2 | 1.14 minutes | 11.3 s |
| EXIOBASE | 100 | over asv's 15-minute limit | 2.25 minutes |

Graph: [bw_graph_tools, traversal](https://simonvanlierde.com/brightway-benchmarks/?page=explorer&group=bw_graph_tools&bench=bench_traversal.Traversal.time_traverse).
Rerun: [`bench_traversal.Traversal`](../benchmarks/bench_bw_graph_tools/bench_traversal.py).

### Without PyPardiso, traversal is hundreds of times slower

**Without PyPardiso, a traversal of the ecoinvent-sized database takes minutes instead of
under a second, and nearly all of it is one factorization.**

[What to do](faster.md).

At `max_calc=2`, a traversal takes 4.6 minutes with SuperLU, against 0.62 s with PyPardiso. On
bw2calc 2.5.0, 234 of its 235 s go to factorizing A. On 3.1.0, which factorizes Aᵀ, it takes
27.8 s. [bw_graph_tools#58](https://github.com/brightway-lca/bw_graph_tools/issues/58) proposes
reusing the LCA's factorization.

Rerun: [`bench_traversal.Traversal`](../benchmarks/bench_bw_graph_tools/bench_traversal.py).

## bw_processing and matrix_utils

### Adding resource groups grows with the square of their number

**The time to add resource groups to a datapackage grows with the square of their number.
[bw_processing#113](https://github.com/brightway-lca/bw_processing/pull/113) removes that, and
cuts building a matrix from 1,000 groups by 42%.** Nothing to do until a release has it.

In every bw_processing release, adding 100 groups takes 2.27 ms, and 1,000 take 273 ms.
matrix_utils 0.9 builds a matrix from 1,000 groups in 724 ms on bw_processing 1.6, and 423 ms
on #113. [matrix_utils#48](https://github.com/brightway-lca/matrix_utils/pull/48) takes those
to 695 and 404 ms. Since 0.6, matrix_utils itself builds 11% slower at 1,000 groups.

Graph: [bw_processing, resource groups](https://simonvanlierde.com/brightway-benchmarks/?page=explorer&group=bw_processing&bench=bench_datapackage.Groups.time_groups).
Rerun: [`bench_datapackage.Groups`](../benchmarks/bench_bw_processing/bench_datapackage.py) and
[`bench_mapped_matrix.MappedMatrixBuild`](../benchmarks/bench_matrix_utils/bench_mapped_matrix.py).

### Smaller bw_processing findings

- **bw_processing 1.6 iterates over 100,000 entries 24% faster**, from 309 to 234 ms.
  Rerun: [`bench_datapackage.EntriesPath`](../benchmarks/bench_bw_processing/bench_datapackage.py).
- **bw_processing stores processed exchange amounts as float32, which moves scores by about
  1e-7**
  ([bw_processing#112](https://github.com/brightway-lca/bw_processing/issues/112)). bw2data's score
  check uses a reference with the same float32 amounts. See
  [`System.float32_reference`](../src/bwbench/synth.py).

## Across packages

### Test suites and dependency floors

The compat `suites` and `floors` columns ([running](running.md#compat)) found these:

- **Three of bw_timex's explicit product-modelling tests fail under pytest 9.2.0**
  ([bw_timex#247](https://github.com/brightway-lca/bw_timex/issues/247)).
- **Five of bw2io 0.9.17's CSV and Excel exporter tests fail with bw2data 4.8**
  ([brightway2-io#354](https://github.com/brightway-lca/brightway2-io/issues/354)).
- **bw_graph_tools 0.10's `test_only_one_node_error_message` fails when PyPardiso is
  installed.** Not reported: an unreleased fix branch is already on bw_graph_tools.
- **On Python 3.12, twelve lower bounds declared by bw2parameters, bw_processing, bw2data,
  bw2calc and bw_timex are too low: the oldest release they allow fails.** If you hold an old
  release of one of these dependencies, raise it to the version that
  [`scripts/compat.sh`](../scripts/compat.sh) lists.

### conda-forge gets releases late

**conda-forge gets a Brightway release only once its feedstock merges the update.** bw2calc
stayed at 2.4.0 there until 3.1.0 landed on 2026-10-18. bw_graph_tools and bw_timex are not
on conda-forge yet. Check the `conda-forge` rows of the
[compatibility view](https://simonvanlierde.com/brightway-benchmarks/?page=compatibility)
before you install from there.
Rerun: `just compat 3.12 conda-forge`.
