# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this
project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- A `codspeed` workflow: every pytest-codspeed suite runs under CodSpeed's CPU simulation on
  pull requests and pushes to `main`, one job per suite, and uploads to CodSpeed, which
  comments on the pull request when an instruction count changes. `scripts/codspeed-venv.sh`
  builds a suite's environment for both this workflow and `just codspeed`.
- A `release` workflow: a pushed `vX.Y.Z` tag creates the GitHub release with the source
  archive, its checksums and a signed build provenance attestation. `CITATION.cff` gives
  the citation, and Zenodo archives each release.
- `.github/CONTRIBUTING.md`: how to report a bug, the checks and tests a pull request needs,
  how dependencies are chosen, and the DCO sign-off, which the new `dco` workflow checks on
  pull requests from forks. SECURITY.md now promises an answer within 14 days and says what
  the project defends against.
- `just compat PYTHON` installs today's PyPI releases of brightway25, bw_graph_tools and
  bw_timex, with no cutoff and no fixed stack, and runs every case once at the smoke size.
  The `compat` workflow runs it nightly on Python 3.12 to 3.14 and keeps the resolved
  `requirements.txt` of each run.
- Two more `just compat` columns, picked by a second argument. `floors` installs the newest
  Brightway packages with each package they depend on at the lowest version their bounds
  allow, so a lower bound set too low fails. `pre` lets pre-releases in, such as NumPy and
  SciPy betas. The `compat` workflow runs `floors` on Python 3.12 and `pre` on 3.14, and
  `latest` on macOS and Windows too. Each run keeps its resolved set in `.asv/compat/PYTHON-COLUMN/`.
- A 60-second Atheris fuzz run of the `release_report.py` result parser on each pull request
  (`.github/workflows/fuzz.yml`).
- Two experimental bw2calc solver environments, run only when named in `BWBENCH_SOLVERS`:
  `klu` (KLU through pyklu, x86_64 only) and `umfpack-T` (scikit-umfpack factorizing Aᵀ).
  Both are patched into bw2calc, and a case fails if bw2calc never called the patched solver.
  `FastScoresOnlyMultiLCA` is skipped under `klu`, as bw2calc needs PyPardiso or UMFPACK for it,
  and in its adjoint direction under `umfpack-T`, which would factorize A there.
- The `noise-hosted` workflow runs `just noise` on a GitHub-hosted runner, so its noise
  floor can be set against the pinned machine's (README, under the noise floor).
- `bw2calc-conda`: the bw2calc suite with NumPy, SciPy, PyPardiso (MKL) and scikit-umfpack
  (SuiteSparse, OpenBLAS) from conda-forge instead of PyPI, at the same versions, for
  bw2calc 2.4.0 and 3.1.0. Its `versions-*.txt` files also list each conda package's build.
  A third environment runs scikit-umfpack on MKL's BLAS (`libblas=*=*_mkl`).
- `peakmem_first_score` (bw2calc) and `peakmem_write` (bw2data) record the process's peak
  resident memory beside the time of the same case, through `@bench(peakmem=True)`.
- `scripts/registry_vs_sqlite.py` prints `peak_rss` (bytes) for each cold read of #290.
- `timeraw` cells that time a cold `import bw2calc` and `import bw2data`, each in a fresh
  interpreter.
- `just noise` logs each sample's CPU time, wall time and involuntary context switches, and
  its summary counts the samples another process preempted (CPU time under 95% of wall time).
- bw2data 4.8 joins the bw2data releases. It needs deepdiff 8.6.2 or later, so the release
  cutoff moves to 2026-10-20 and bw2data's fixed stack is resolved again from 4.8 (deepdiff
  9.1.0, peewee 4.5.3, pydantic 2.14). All six bw2data releases from 4.6 still run every case
  on it, but their timings start a new history on the new stack. The cutoff also applies to
  the packages `just solver-lci` and `just registry-vs-sqlite` leave unpinned, and both now get
  bw2calc 3.1.0 and bw2data 4.8 without per-package exceptions.
- bw2calc 3.1.0 joins the bw2calc releases. Its new minimum versions of bw_processing and
  matrix_utils are already in the fixed stack, so the older releases keep their history.
- `just solver-lci SOLVER SIZE [BW2CALC]` times bw2calc's own `lci()` (3.1.0 unless you name
  another release) with SuperLU, UMFPACK, PyPardiso, or, patched in, UMFPACK on Aᵀ and KLU
  (pyklu), and checks each score. The `solvers-macos` workflow runs it on an Apple Silicon
  runner, where PyPardiso cannot install, for the release you pick.
- `scripts/solver_factorize.py` times one factorization and one solve of the real ecoinvent
  matrix with SuperLU, UMFPACK, KLU and PyPardiso, for anyone with an ecoinvent licence.
  It names the BLAS libraries it loaded, and runs in a conda environment without pyklu too.
- Each package's history page links back to the front page, from a first tab in asv's menu.
- `measure()` also factorizes Aᵀ, under both column orderings: bw2calc's
  `decompose_technosphere` factorizes A, while scipy's `spsolve` on a CSR matrix factorizes Aᵀ.
  Their keys end in `(A^T)`.
- The history site's front page says what each history times and how to read the graphs,
  in light and dark mode, and links bw2calc's time for one score as the place to start.
- The first results in the README: bw2calc 2.0 to 3.0.0 at the ecoinvent size, with 3.0.0's
  `IterativeLCA` slowdown without PyPardiso.
- Why bw_graph_tools on EXIOBASE takes 11.3 s at `max_calc` 2 and 2.25 minutes at 100, though
  both count 16 calculations: the counter counts nodes created, not solves, and is checked only
  before the next node is expanded. Both runs create the same 16 nodes in the second expansion;
  at 2 the traversal stops there (392 right-hand sides solved), at 100 it expands all 16, each
  solving its ~390 inputs (4,922 right-hand sides). Time follows the right-hand-side count:
  about 12 ms each with PyPardiso, 51 ms with SuperLU. A transposed unit-score solve makes it
  one solve either way (0.21 s against 0.33 s).
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
- A comparison of a bw2data SQLite project with the Parquet registry of bw2data #290. At the
  ecoinvent size (2026-10-18, single runs, no PyPardiso): write 10.6 s and 123 MB for SQLite,
  1.04 s and 16.7 MB for the registry with `bw_package/`, 0.96 s and 6.5 MB for its Parquet
  tables alone; first scores 18.0 to 20.0 s, all of it SuperLU's factorization. DuckDB's
  narrower lookup saves 0.27 s at smoke size and nothing visible there.
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

### Changed

- `just registry-vs-sqlite` runs bw2data 4.8 and bw2calc 3.1.0. The box's release cutoff had
  held it at bw2data 4.7 and bw2calc 2.5.0. `solver=pypardiso` adds PyPardiso, and each row
  names the solver bw2calc used.
- PyPI environments no longer write a `versions-*.txt` file beside the results: their
  `pylock.*.toml` lock file holds the same versions. Only the conda environments
  (`bw2calc-conda`) keep one, as they have no lock file. The PyPI versions
  files already published stay, and no longer change.
- bw2data's score check (`DatabaseWrite.track_score_error` and the SQLite row of
  `just registry-vs-sqlite`) compares against a reference built from amounts rounded to
  float32, since bw_processing 1.6 stores them that way
  ([bw_processing#112](https://github.com/brightway-lca/bw_processing/issues/112)), and
  `BW2DATA_RTOL` drops from 1e-6 to 1e-12. From this version on, `track_score_error` falls
  from about 3e-9 (smoke) and 5.7e-8 (ecoinvent size) to about 1e-15: a step in the published
  history, not a change in bw2data.

### Fixed

- `just registry-vs-sqlite solver=pypardiso` fell back to SuperLU without a word, because
  pypardiso looks for MKL in `sys.prefix` only, which `uv run --with` puts elsewhere. It now
  points pypardiso at the `mkl` package's runtime through `bwbench.point_pypardiso_at_mkl()`,
  which `solver_lci.py` and `solver_factorize.py` share instead of their own copies.
- `scripts/in-box.sh` works in a git worktree, whose `.git` file points outside the mounted
  folder: it runs `git config` from `/`.

[Unreleased]: https://github.com/simonvanlierde/brightway-benchmarks/commits/HEAD
