# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this
project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `just solver-lci SOLVER SIZE` times bw2calc 3.0.0's own `lci()` with SuperLU, UMFPACK,
  PyPardiso, or, patched in, UMFPACK on Aᵀ and KLU (pyklu), and checks each score. The
  `solvers-macos` workflow runs it on an Apple Silicon runner, where PyPardiso cannot install.
- `measure()` also factorizes Aᵀ, under both column orderings: bw2calc's
  `decompose_technosphere` factorizes A, while scipy's `spsolve` on a CSR matrix factorizes Aᵀ.
  Their keys end in `(A^T)`.
- The history site's front page says what each history times and how to read the graphs,
  in light and dark mode, and links bw2calc's time for one score as the place to start.
- The first results in the README: bw2calc 2.0 to 3.0.0 at the ecoinvent size, with 3.0.0's
  `IterativeLCA` slowdown without PyPardiso.
- asv suites for bw2calc, bw2data, bw_processing, matrix_utils, bw_graph_tools and bw_timex,
  run over their released versions. Every case except bw_processing's two `EntriesPath`
  cases checks its result against a float64 reference.
- A seeded generator of synthetic LCA systems, `system(profile, seed=..., **overrides)`,
  written as bw_processing datapackages or bw2data databases. The `ecoinvent` profile copies
  the structure of ecoinvent 3.12 cut-off: loops, hub suppliers, region and sector locality,
  waste treatments and per-product units. `smoke`, `mc100k` and `regional` scale it to 200,
  100k and 250k products. `exiobase` and `stress-random` use a random structure.
- `measure()`, the structural statistics of a technosphere matrix. It calibrates and checks
  the generator, and reports what drives LU fill: rows near COLAMD's dense cut-off,
  nnz(AᵀA), clustering, reciprocity, the 2-core left without hubs, and fill and pivots without
  partial pivoting. It also locates the consumer overlap: per band of supplier size, among the
  50 largest suppliers (`hub_jaccard`) and without them (`overlap_without_hubs`), and how
  many products copy another's input list.
- Profiles publish quantiles only: no minimum, maximum or mean, each of which can be one
  dataset's figure. The `ecoinvent` profile credits ecoinvent.
- `measure_stats.py --structure-only` updates a profile's structure in about a minute and
  keeps the fill figures it already holds, with the date they were measured.
- matrix_utils #48 as its own line in the history (the asv branch `pull/48/head`), until a
  release includes it.
- `@bench`: write a benchmark once, as a setup that returns the timed call and its check,
  and run it under asv or pytest-codspeed. A setup that needs a teardown yields instead.
- Next to each machine's results, a PEP 751 lock file per asv environment. At the results
  root, an RO-Crate `ro-crate-metadata.json` over all of them that names the bwbench commit,
  the generator version and the profiles.
- A comparison of a bw2data SQLite project with the Parquet registry of bw2data #290.
- `just smoke`, `just bench`, `just site` and `just registry-vs-sqlite`. Each runs in a
  throwaway container.
- A weekly smoke run in CI, over each package's oldest and latest release.
- One fixed set of dependencies per package (`asv/<package>.stack.txt`): every release is
  benchmarked on its latest release's dependencies, so only the package changes along the
  history. `just stack` resolves the set, `just stack-check` shows which releases still run
  on it. bw2data's history starts at 4.6 and bw_timex's at 1.1.0 for that reason.
- `just noise`, the run-to-run spread per case. It is about 1% at the ecoinvent size.
- `BWBENCH_SOLVERS` picks the solver environments (`superlu`, `pypardiso`, `umfpack`), and
  bw_graph_tools gets a PyPardiso environment.
- `just bench` skips what already succeeded, so a stopped backfill resumes.
- `just results-commit` keeps results as data on a local `results` branch, and a `site`
  workflow builds the history site from that branch and publishes it on GitHub Pages. The
  recipe adds and updates files but never deletes another machine's, and refuses results
  whose folder names or file contents name the host, so set `BWBENCH_MACHINE` (and list
  other private names in `BWBENCH_PRIVATE_NAMES`).
- Skips, with the upstream link, for bw2calc cases that a release crashes on for a reported
  reason: `IterativeLCA`'s second solve where scipy rejects `atol="legacy"`, and
  `FastScoresOnlyMultiLCA` and `JacobiGMRESLCA` Monte Carlo with PyPardiso (bw2calc #157).
  A release with the fix runs them again. bw2calc 3.0.0 fixes both and runs those cases.
- bw2calc 3.0.0 in the history. Its new dependency, threadpoolctl 3.7.0, is installed beside
  the fixed set rather than in it, so the older releases' history does not restart.
- Skips for cases whose SuperLU or UMFPACK factorizations would overrun the timeout without
  PyPardiso, estimated from the profile's size: the 100k and 250k profiles, and `LCA` Monte
  Carlo from the ecoinvent size up. `JacobiGMRESLCA` solves by GMRES and is never skipped.
- A warning when numpy is imported before `bwbench`, because the BLAS thread pin then comes
  too late.

[Unreleased]: https://github.com/simonvanlierde/brightway-benchmarks/commits/HEAD
