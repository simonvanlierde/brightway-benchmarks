# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this
project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- **Breaking:** the synthetic generator is at version 4, so every benchmark's history starts again
  from the rerun that follows it. Earlier times stay in the results branch's git history
  ([method](docs/method.md#how-the-results-stay-reproducible)).
- A run at one database size keeps the other sizes' results instead of replacing them.

### Added

- BAFU 2025, the Swiss Federal Administration's LCI database, as a real size beside USEEIO
  (`BWBENCH_SIZES=bafu`). It is downloaded once and never copied into this repository
  ([real databases](docs/method.md#the-real-databases)).
- A [solver-choice story](https://simonvanlierde.com/brightway-benchmarks/stories/solver-choice/):
  what to install for a fast bw2calc on conda, pip, uv or Apple silicon, with the real-ecoinvent times
  behind it.
- A [cuDSS finding](docs/findings.md#cudss-refactorizes-real-ecoinvent-in-37-ms-but-that-isnt-a-monte-carlo-draw-yet):
  GPU factorization times on real ecoinvent next to the CPU solvers, and what they don't cover.
- `BWBENCH_ENERGY=1` logs each timed sample's CPU package energy on Intel CPUs, and
  `scripts/energy_summary.py` gives the joules and watts per case. The numbers stay local
  ([running](docs/running.md#energy-per-operation)).
- `just profile` runs one benchmark case under pyinstrument, and findings link the profiles behind
  them ([running](docs/running.md#benchmarks)).
- Guidance on [contributing a run](docs/running.md#contribute-a-run) from your own machine.
- bw_processing and matrix_utils time 10,000 resource groups in full-size runs.
- Measurements of what bounds LU fill (METIS fill of A + Aᵀ, the top separator), so the synthetic
  profile can be checked against real databases
  ([#54](https://github.com/simonvanlierde/brightway-benchmarks/issues/54)).
- The viewer links each subject to its Brightway docs and each benchmark to its CodSpeed page.

### Removed

- The experimental input-sharing controls in the generator (`copies`, `bundles`, `copy_long`,
  `markets`, `market_by`, `same_region_by_length`). None was on in a registered profile, and none
  brought the fill down ([what did not lower the fill](docs/method.md#what-did-not-lower-the-fill)).

## [0.2.0] - 2026-11-01

### Added

- A benchmark viewer with Setup and Benchmarks pages, searchable histories, release comparisons,
  solver evidence and linked findings. It includes accessible charts and data tables, phone layouts,
  a theme switch, sharing previews and project metadata ([viewer](ui/README.md)).
- Dated installation sets for uv, pip, conda and pixi, retained beyond workflow artifact expiry.
  Setup shows each check’s latest result and last passing set, including failed checks and coverage
  limits ([installation sets](docs/running.md#install-a-set-that-works)).
- A 39-job nightly compatibility matrix covering Python 3.12, 3.13 and 3.14 on Linux, macOS and
  Windows, including dependency floors, pre-releases and upstream test suites. Conda checks remain
  Linux-only ([coverage](docs/running.md#the-nightly-runs)).
- Compatibility reports identify new failures, recoveries and continuing failures. Failed diagnostic
  jobs retain an upstream issue draft for a person to review and post
  ([compatibility reports](docs/running.md#report-newly-failing-jobs)).
- USEEIO 1.1 as a public-domain input for bw2calc benchmarks, fetched by a pinned checksum and checked
  against a reference solve ([real database](docs/method.md#the-real-databases)).
- Synthetic ecoSpold2 import benchmarks that require no ecoinvent licence, plus optional benchmarks
  of a licensed release. The import checks that every exchange links ([method](docs/method.md)).
- Experimental controls for shared input lists and locality, with seed-by-seed calibration reports.
  These controls remain off in registered profiles ([calibration](docs/calibration-sweep.md)).
- GPU factorization and fixed-sparsity update probes for cuDSS, PARDISO analysis reuse timings, and
  a benchmark of UMFPACK iterative refinement ([method](docs/method.md)).
- A versioned JSON export for the viewer, including benchmark explanations, release changes beyond
  measurement noise and Apache Otava change points ([viewer data](ui/README.md#the-data)).
- Findings and installation guidance explaining measured regressions and solver choices, including
  the Monte Carlo slowdown in JacobiGMRESLCA ([findings](docs/findings.md),
  [faster workflows](docs/faster.md)).
- A project DOI, governance and contribution guidance, roadmap and security assurance case
  ([assurance case](docs/assurance-case.md)).

### Changed

- The README is a project overview; findings, methods and operating instructions now have their own
  pages ([running](docs/running.md)).
- Dependency-floor checks use corrected lower bounds for the tested Brightway packages
  ([compatibility checks](docs/running.md#compat)).
- Release comparisons use each case’s measured spread, distinguish fixed-stack changes and keep
  hash-only experiments out of release summaries ([release comparisons](ui/README.md#what-it-shows)).

### Fixed

- Selecting a compatibility check keeps its Python version, install command and URL aligned;
  changing package manager no longer silently switches Python ([viewer](ui/README.md#what-it-shows)).
- Archived installation sets preserve their latest passing date and run after artifacts expire,
  and pylock files accept supported Python patch releases older than the CI runner’s
  ([archive](docs/running.md#the-compat-archive)).
- Sampling an import from a relative ecoinvent release folder now keeps readable links to its
  datasets and MasterData ([import benchmarks](docs/method.md)).
- Missing interpreters in old asv environments no longer fail an otherwise completed run when
  installation versions are collected ([running](docs/running.md#benchmarks)).

### Security

- Compatibility installation sets are accepted only from this repository’s main-branch compatibility
  workflow, with repository and workflow provenance checked before artifact downloads
  ([trust boundaries](docs/assurance-case.md#trust-boundaries)).
- Viewer data exports reject symlink output paths before deleting or writing files, protecting
  host files from links planted in container-writable output folders
  ([trust boundaries](docs/assurance-case.md#trust-boundaries)).

### Removed

- The asv-generated history pages. Existing links redirect to the new benchmark explorer
  ([viewer](ui/README.md#what-it-shows)).

## [0.1.0] - 2026-10-28

The first release. It times six Brightway packages over their released versions on seeded
synthetic databases, checks each LCA score against an independent reference, and publishes
the history on GitHub Pages. The README describes what is measured and how to run it.

### Added

- **Benchmarks.** asv suites for bw2calc (2.0 to 3.1.0), bw2data (4.6 to 4.8), bw_processing,
  matrix_utils, bw_graph_tools and bw_timex (from 1.1.0), each over its released versions on
  one fixed set of dependencies (`asv/<package>.stack.txt`), so only the package changes along
  a history. `just stack` resolves the set and `just stack-check` shows which releases still
  run on it. Cells cover a first score, a second functional unit, many functional units at
  once, Monte Carlo, database writes, graph traversal, datapackage and matrix building, the
  time-explicit LCI, peak memory (`peakmem_*`) and cold import time (`timeraw_*`).
- **Checks.** Each LCA score is checked against a reference that uses no Brightway code, so
  a fast but wrong release fails. Monte Carlo draws are checked only for finite values and
  bw_timex against bw2calc's own score; the builder and traversal cases have no score to
  check. bw2data's reference uses amounts rounded to float32, as bw_processing 1.6 stores
  them ([bw_processing#112](https://github.com/brightway-lca/bw_processing/issues/112)).
  Cases a release crashes on for a reported upstream reason are skipped with the link, and
  run again in a release with the fix.
- **Solvers.** `BWBENCH_SOLVERS` picks bw2calc's and bw_graph_tools' solver environments:
  `superlu`, `pypardiso` and `umfpack`, plus the experimental `klu` and `umfpack-T`, which
  are patched into bw2calc (a case fails if bw2calc never reached the patch).
  `bw2calc-conda` runs the bw2calc suite on conda-forge's NumPy, SciPy, PyPardiso and
  scikit-umfpack (OpenBLAS and MKL BLAS) for bw2calc 2.4.0 and 3.1.0. `just solver-lci`
  times bw2calc's own `lci()` with one solver, and the `solvers-macos` workflow runs it on
  Apple Silicon. `scripts/solver_factorize.py` times the real ecoinvent matrix for anyone
  with a licence.
- **Synthetic databases.** `system(profile, seed=...)` generates an LCA system as
  bw_processing datapackages or a bw2data database. The `ecoinvent` profile copies the
  structure of ecoinvent 3.12 cut-off (loops, hub suppliers, locality, waste treatments,
  units) from published quantiles only; `smoke`, `mc100k`, `regional`, `exiobase` and
  `stress-random` cover other sizes and structures. `measure()` reports the statistics that
  calibrate the profile and drive LU fill, and `measure_stats.py` refreshes a profile.
- **Running it.** `just smoke`, `just bench`, `just noise`, `just site`, `just
  results-commit`, `just registry-vs-sqlite` and `just codspeed`. Brightway's code runs only
  in a throwaway container with the repository read-only, no capabilities, a new home folder
  and no uv or pip config each run, and limits from `BWBENCH_CPUS`, `BWBENCH_MEM` and
  `BWBENCH_THREADS`. `BWBENCH_SIZES` and its per-case
  variants pick the database size, and `BWBENCH_ROUNDS` the rounds. `just bench` skips what
  already succeeded, so a stopped backfill resumes. `@bench` writes a case once for both asv
  and pytest-codspeed; `just codspeed` runs a suite under CodSpeed's CPU simulation with
  address randomization off (`docker/seccomp-noaslr.json`).
- **Reproducible results.** Each run keeps a PEP 751 lock file per environment (a
  `versions-*.txt` with build strings for conda) and a `bwbench-run-*.txt` record of the
  commit and generator version that wrote each file. The RO-Crate over the results credits
  each file to that commit and names the profiles. `just noise` measures the run-to-run spread per case; the
  README gives the noise floor on the pinned machine and on a hosted runner
  (`noise-hosted` workflow).
- **Publishing.** `just results-commit` keeps results on a `results` branch, refusing any that
  name the host or a name in `BWBENCH_PRIVATE_NAMES`, and the `site` workflow builds the
  history pages from it, daily and after new results. The front page says how to read the graphs and, from the nightly
  `compat` runs, which Brightway set works together today, with its `requirements.txt` and
  `pylock.toml`.
- **Compatibility.** `just compat PYTHON [latest|floors|pre]` installs today's PyPI releases
  of brightway25, bw_graph_tools and bw_timex, at the newest versions, at their dependencies'
  declared floors, or with pre-releases, and runs every case once. The `compat` workflow runs
  it nightly on Linux (Python 3.12 to 3.14), macOS and Windows.
- **Project.** CONTRIBUTING.md, SECURITY.md with a 14-day answer and a security assessment,
  CITATION.cff, and workflows for checks, a weekly smoke run, CodSpeed on pull requests,
  Atheris fuzzing of the result parser, OpenSSF Scorecard, the DCO sign-off on fork pull
  requests, and releases with a signed provenance attestation.

### Changed

For readers of the history pages, which were published before this release:

- bw2data's score check moved to the float32 reference above, and its tolerance from 1e-6 to
  1e-12, so `track_score_error` drops from about 5.7e-8 at the ecoinvent size to about
  1e-15. That is a step in the published history, not a change in bw2data.
- bw2data 4.8 moved the release cutoff to 2026-10-20 and re-resolved bw2data's fixed stack
  (deepdiff 9.1.0, peewee 4.5.3, pydantic 2.14), so bw2data's timings start a new history.
- PyPI environments no longer write `versions-*.txt` beside their results: the lock file
  holds the same versions. The files already published stay.
- The published RO-Crate credits each result file to the commit that wrote it. Files written
  before the run records existed show the commit as `unknown`, where the crate used to name
  whatever commit last wrote it.

[Unreleased]: https://github.com/simonvanlierde/brightway-benchmarks/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/simonvanlierde/brightway-benchmarks/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/simonvanlierde/brightway-benchmarks/releases/tag/v0.1.0
