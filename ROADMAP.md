# Roadmap

What is planned for brightway-benchmarks over the next year, to October 2027, in rough order. It
is a plan, not a promise, and none of it has a date. Released work is in
[CHANGELOG.md](CHANGELOG.md), and [GOVERNANCE.md](.github/GOVERNANCE.md) says who decides what goes
here. Ideas and bugs go in [GitHub issues](https://github.com/simonvanlierde/brightway-benchmarks/issues).

## Planned

- **Rerun the histories with generator v5.** Activity families now bring mean METIS fill to
  37.9 against ecoinvent's 30.9, passing the calibration guards over four seeds
  ([calibration](docs/generator-calibration.md)). The published histories still use v4, whose
  higher fill overstates direct-solver times. Rerun every minor line and update the findings
  and solver story ([#54](https://github.com/simonvanlierde/brightway-benchmarks/issues/54)).
- **Our own results UI,** replacing asv's pages: what changed in each release against the
  measured noise, each benchmark's history, and comparisons across solvers and environments
  ([decision 0001](docs/decisions/0001-own-benchmark-ui.md)).
- **The synthetic inputs as a dataset** on Zenodo, one version per generator version, so the
  matrices and ecoSpold2 files can be used without running the generator. `just dataset` builds
  it ([running](docs/running.md#publish-the-synthetic-inputs)); nothing is deposited yet.
- **More solver columns for bw2calc:** NVIDIA cuDSS behind a GPU opt-in, kept out of the default
  run (`scripts/solver_factorize.py --cudss` already times it on real ecoinvent), and Apple's
  Accelerate LU on macOS.
- **Continuous runs on contributed machines:** when someone offers a machine for regular runs,
  a [Bencher](https://bencher.dev) self-hosted runner on it, beside the result files
  contributors add by hand now ([running](docs/running.md#contribute-a-run)).
- **bw2data's write path:** the SQLite database against the Parquet tables proposed for a
  registry, with time and peak memory at ecoinvent size.
- **bw_timex at a larger timeline,** so the timeline builder, not the graph traversal, sets the
  time.
- **Benchmarks upstream:** propose a `benchmarks/` folder with a smoke mode and a pull request job
  to bw2calc, built from the cases here.
- **A write-up of the results so far,** archived on Zenodo with the release it describes.

## Waiting on upstream

- The MKL search that bw2calc 3.x pays for on every LCA object under PyPardiso
  ([#56](https://github.com/simonvanlierde/brightway-benchmarks/issues/56)). The fix belongs in
  PyPardiso; the history will show the gain once the pinned stack moves to a release with it.
- Declared dependency floors that are too low, which the `floors` compat column finds. Each is
  reported to its package.

## Not planned

- Timing unreleased Brightway code by default. Commits are timed only by hand, so the history
  shows what users install.
- Running this project's own benchmarks outside the throwaway benchmark box. Hosted and
  contributed ratio runs are the exceptions ([where it runs](docs/architecture.md#where-it-runs)).
- Real ecoinvent data in the repository. The profiles hold only aggregate statistics.
