# Make your Brightway faster

Gains are on the ecoinvent-sized synthetic database, one thread, unless the row says otherwise.

| Situation | Install or call | Gain, and the release measured | Finding |
| --- | --- | --- | --- |
| Any score | scikit-umfpack from conda-forge, without PyPardiso: bw2calc uses PyPardiso whenever it is installed, and bw_timex pulls it in on Linux x86_64. Without conda, PyPardiso on x86_64. | A score takes 2.63 s, against 10.0 s with PyPardiso and 27.7 s with SciPy's SuperLU. bw2calc 3.1.0. | [Solver](findings.md#the-solver-sets-the-time-for-one-score) |
| You build scikit-umfpack yourself | Link it to OpenBLAS or MKL, not reference BLAS. | Factorizing real ecoinvent 3.12 takes 0.63 s on MKL, against 1.79 s on reference BLAS. bw2calc 3.1.0. | [BLAS](findings.md#umfpacks-speed-depends-on-its-blas-and-its-refinement-step) |
| Many functional units, with UMFPACK or SuperLU | `lca.lci(factorize=True)` once, then `lca.lci(demand=...)` for each unit. Needs bw2calc 3.1.0 or later. PyPardiso ignores `factorize=True`: it keeps its own. | Each unit after the first takes 33.6 ms, against 9.06 s, with UMFPACK. bw2calc 3.1.0. | [Factorization](findings.md#keep-the-factorization-for-repeated-solves) |
| Many solves with UMFPACK on reference BLAS or OpenBLAS | Turn off iterative refinement (`UMFPACK_IRSTEP`). bw2calc has no switch for it yet: [brightway2-calc#184](https://github.com/brightway-lca/brightway2-calc/issues/184) proposes one. | A solve on real ecoinvent 3.12 takes 3.7 ms, against 10.5 ms, on reference BLAS. bw2calc 3.1.0. | [Refinement](findings.md#umfpacks-speed-depends-on-its-blas-and-its-refinement-step) |
| Many LCA objects under PyPardiso | Set `PYPARDISO_MKL_RT` to the path of MKL's `mkl_rt` library. | A smoke-size first score takes 2.7 ms, against 37 ms. bw2calc 3.1.0. | [MKL search](findings.md#every-new-lca-object-under-pypardiso-searches-for-mkl-again) |
| Graph traversal with bw_graph_tools | Install PyPardiso. Without it, use bw2calc 3.1.0 or later. | A traversal at `max_calc=2` takes 0.62 s, against 4.6 minutes with SuperLU. bw_graph_tools 0.8, bw2calc 2.5.0. | [Traversal](findings.md#without-pypardiso-traversal-is-hundreds-of-times-slower) |

In bw2calc 3.1.0, `redo_lci(demand)` does what `lci(demand=...)` does, with a deprecation warning.
