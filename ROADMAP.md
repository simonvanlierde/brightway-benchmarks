# Roadmap

What is planned for brightway-benchmarks over the next year, to October 2027, in rough order. It
is a plan, not a promise, and none of it has a date. Released work is in
[CHANGELOG.md](CHANGELOG.md), and [GOVERNANCE.md](.github/GOVERNANCE.md) says who decides what goes
here. Ideas and bugs go in [GitHub issues](https://github.com/simonvanlierde/brightway-benchmarks/issues).

## Planned

- **A more faithful `ecoinvent` profile.** Its LU fill is too high, so SuperLU times on it
  overstate real ecoinvent ([#54](https://github.com/simonvanlierde/brightway-benchmarks/issues/54)).
  The next step is to measure how long the copied input lists are.
- **More solver columns for bw2calc:** NVIDIA cuDSS behind a GPU opt-in, kept out of the default
  run, and Apple's Accelerate LU on macOS.
- **Scaling cells for bw_processing:** how the time to read a datapackage grows with the number of
  resource groups, from 1,000 to 10,000.
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
- Running Brightway's code outside the throwaway benchmark box.
- Real ecoinvent data in the repository. The profiles hold only aggregate statistics.
