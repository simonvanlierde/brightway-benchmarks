# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this
project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- A table of what moved in each package's latest release: every case whose time or memory
  changed more than 5% since the release before, per environment, including cases that failed
  before and run now. It is on the site's front page, and `just release-changes bw2calc`
  prints it as Markdown to paste into an upstream issue. A row says "stack moved" when the
  two releases ran on different fixed dependencies.
- A bw2calc case, `NewDemandRefinement`, that times `redo_lci` with UMFPACK's iterative
  refinement on (its default) and off (`UMFPACK_IRSTEP=0`). It records the refinement steps
  taken and checks the score against the reference either way. It runs only in the UMFPACK
  environment.
- A DOI for citing the project, 10.5281/zenodo.23727602, in `CITATION.cff` and as a README
  badge. It always points at the latest release.
- A roadmap (ROADMAP.md), a governance page that says who decides and what happens if the
  maintainer is unavailable, a code of conduct, and an assurance case
  (docs/assurance-case.md) that ties each security claim to the code that backs it.
- SECURITY.md says which releases get fixes: only the newest.
- A `conda-forge` compat column: each night the Brightway set is installed from conda-forge
  with pixi and its cases run on Python 3.12, since conda-forge gets releases later than PyPI
  and breaks separately. Run it with `just compat 3.12 conda-forge`. The bw_graph_tools and
  bw_timex cases are left out until those packages are on conda-forge. The site table shows
  the last set that passed, with a `pixi.toml` and `pixi.lock` to install it.
- CI fails when test coverage drops below 80%. Coverage now counts the scripts the tests run
  as subprocesses, leaving out the three that only run inside the benchmark box.
- A `suites` compat column (`just compat 3.12 suites`) runs the test suites of bw2data,
  bw2calc, bw2io, bw_processing, matrix_utils, bw_graph_tools and bw_timex against the
  newest releases, every night on Python 3.12. A dependency release that breaks a package's
  own tests shows up the next morning, with the failing tests in the job summary, even when
  that package's CI has not run since. Like `floors` and `pre`, it does not turn the run red.

### Changed

- The README is now a short overview. What the benchmarks found, with what each finding means
  for you and its upstream issue, moved to docs/findings.md; what is measured and how far to
  trust a step to docs/method.md; and how to run the benchmarks and compat checks, with every
  `BWBENCH_*` variable, to docs/running.md.
- The `floors` compat column raises twelve declared floors found too low on Python 3.12 to
  the oldest release that passes, so it runs every case again and catches the next one. They
  are in bw2parameters, bw_processing, bw2data, bw2calc and bw_timex; `scripts/compat.sh`
  lists them.

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

[Unreleased]: https://github.com/simonvanlierde/brightway-benchmarks/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/simonvanlierde/brightway-benchmarks/releases/tag/v0.1.0
