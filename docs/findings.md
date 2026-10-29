# Findings

What the benchmark histories show so far, package by package.

## bw2calc

The history pages are at <https://simonvanlierde.com/brightway-benchmarks/>.
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

## The other packages

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
  reported upstream as brightway2-data#306. The score after the write matches the reference in every
  release; the reference rounds amounts to float32, as bw_processing stores them
  ([bw_processing#112](https://github.com/brightway-lca/bw_processing/issues/112)).
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
