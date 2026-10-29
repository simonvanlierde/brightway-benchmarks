# Method

Results are in [findings.md](findings.md), how to run the benchmarks in
[running.md](running.md).

## What is measured

- bw2calc: one score; a second functional unit, with UMFPACK's refinement on and off; many
  functional units against three impact categories; Monte Carlo draws; `import bw2calc`. Each
  runs with the direct solvers (PyPardiso, UMFPACK, SuperLU) and the iterative ones.
- bw2data: writing a database, up to ecoinvent's size; `import bw2data`.
- bw_processing and matrix_utils: building datapackages and matrices from many resource groups.
- bw_graph_tools: supply-chain graph traversal.
- bw_timex: the time-explicit LCI as the timeline grows.

Each score is checked against a reference that uses no Brightway code, so a fast but wrong
release fails. Monte Carlo draws are checked only for finite values, and bw_timex against
bw2calc's score.

## The synthetic databases

A database is generated from a seed, so the same settings give the same matrices everywhere.
Its shape comes from a profile:

- `ecoinvent`: 26,533 products, like ecoinvent 3.12 cut-off, with its measured inputs per
  process and consumers per product, one loop holding 64% of the products, negative waste
  inputs, and a spectral radius of 0.78.
- `smoke`: the same structure at 200 products.
- `mc100k` and `regional`: 100,000 and 250,000 products.
- `exiobase` and `stress-random`: a random structure, a worst case for the solvers.

Only aggregate statistics of the ecoinvent database (ecoinvent Association) went into the
`ecoinvent` profile, no dataset or figure of one. They are in
[`src/bwbench/profiles/`](../src/bwbench/profiles).

The profile is harder on a direct solver than real ecoinvent: SuperLU's factors hold 323 times
as many entries as the matrix, against 175 for ecoinvent. So SuperLU times overstate real
ecoinvent ([#54](https://github.com/simonvanlierde/brightway-benchmarks/issues/54)). With a
licence of your own, [`scripts/solver_factorize.py`](../scripts/solver_factorize.py) times each
direct solver on the real matrix.

## How the results stay reproducible

- [asv](https://asv.readthedocs.io) runs every release of a package on one fixed set of
  dependencies, from before 2026-10-20, in `asv/<package>.stack.txt`. So a step in a graph is
  that package's own change. bw2calc 3.0.0 and later also get threadpoolctl.
- Each history starts at the oldest release that runs on that set: bw2data at 4.6 (peewee 4),
  bw_timex at 1.1.0. Every release of the other packages runs.
- Each run records what was installed (`pylock.toml`) and an RO-Crate naming the code and
  settings.
- CodSpeed turns address randomization (ASLR) off, which needs
  [`docker/seccomp-noaslr.json`](../docker/seccomp-noaslr.json) in the box.

## The noise floor

A step is a real change only if it is larger than the noise between runs. The spread of a case
is the interquartile range of its samples relative to the median. `just noise` measures it
([running.md](running.md#measure-the-noise)).

On a pinned benchmark machine, on 8 efficiency cores:

- asv, bw2calc's first score at the ecoinvent size under PyPardiso, six runs: 0.0% with ASLR
  on, 0.1% off.
- CodSpeed, the traversal cases, three runs: 0.035% and 0.014% with ASLR off, 0.7 to 1.1% on.
- asv, smoke size, 10 runs: up to 4%, median 0.9%.

So a step of 5% or more at the ecoinvent size is real. ASLR stays on for asv, where it changes
nothing measurable. Cases of a few milliseconds vary more, and up to five-fold unless the CPU
runs its performance power profile (`powerprofilesctl set performance` on Linux).

bw2data's write stalls for 16 to 17 s in 1 or 2 samples in 12, while the host flushes its disk
cache. asv's median doesn't move.

**A GitHub-hosted runner hides changes under about 15%.** On `ubuntu-latest` (the
`noise-hosted` workflow), the same smoke cases spread 1 to 14%, median 4.0%. It would catch a
several-fold step such as bw2calc 3.0.0's, but not a small one.
