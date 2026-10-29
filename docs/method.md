# Method

What the benchmarks measure, the databases they run on, and how the results stay comparable.

## What is measured

| Package | What is timed, in LCA terms |
| --- | --- |
| bw2calc | One score (build the matrices, solve, characterize); a second functional unit on a solved system; many functional units against three impact categories; Monte Carlo draws; a cold `import bw2calc` |
| bw2data | Writing a database, up to the size of ecoinvent; a cold `import bw2data` |
| bw_processing, matrix_utils | Building datapackages and matrices from many resource groups |
| bw_graph_tools | Supply-chain graph traversal, small and large |
| bw_timex | The time-explicit LCI as the timeline grows |

bw2calc runs each case with the direct solvers (PyPardiso, UMFPACK, SuperLU) and with its
iterative solvers.

Each LCA score is checked next to its timing, against a reference that uses no Brightway
code at all. So a fast but wrong release fails instead of looking good. Two kinds of case
are checked more loosely: Monte Carlo draws only for finite values, and bw_timex against
bw2calc's own score. The cases that only build datapackages, matrices or a graph traversal
have no score to check, and neither do the import cells.


## The synthetic databases

A database is generated from a seed, so the same settings give the same matrices on every
machine. Its shape comes from a profile:

- `ecoinvent` has 26,533 products, like ecoinvent 3.12 cut-off, and copies that release's
  measured structure: how many inputs each process has and how many consumers each product
  has; one large loop that holds 64% of the products; waste treatments with negative
  inputs; units that span many orders of magnitude; and a spectral radius of 0.78, which
  sets how fast the supply-chain series converges. Only aggregate statistics of ecoinvent
  went into it, calculated from the ecoinvent database (ecoinvent Association), never a
  dataset or a figure of a single dataset. They are in [`src/bwbench/profiles/`](../src/bwbench/profiles).
- `smoke` is the same structure at 200 products, for quick checks.
- `mc100k` and `regional` scale it to 100,000 and 250,000 products, the sizes of a large
  Monte Carlo study and a regionalised database.
- `exiobase` and `stress-random` use a random structure, a worst case for the solvers.

One known difference: a direct solver needs more memory and time for the `ecoinvent`
profile than for the real ecoinvent. SuperLU's factors hold 323 times as many entries as
the matrix, against 175 for ecoinvent. The likely cause: the real database's suppliers
share more of their consumers. [#54](https://github.com/simonvanlierde/brightway-benchmarks/issues/54) tracks the work on it.
With a licence of your own, [`scripts/solver_factorize.py`](../scripts/solver_factorize.py) times
each direct solver on the real ecoinvent matrix instead, and prints timings only.

## How the results stay reproducible

- [asv](https://asv.readthedocs.io) runs every release of a package on one fixed set of
  dependencies: those of its latest release, from before 2026-10-20, listed in
  `asv/<package>.stack.txt`. Only the package itself changes from one point in the history
  to the next, so a step in a graph is that package's change. One exception: bw2calc 3.0.0 and later
  need threadpoolctl, which its asv config installs beside the set, so that the older
  releases keep their history. They never import it.
- Each history starts at the oldest release that runs on that set. bw2data starts at 4.6,
  the first release on peewee 4, which older ones cannot import. bw_timex starts at 1.1.0,
  since 1.0.0 fails a check that bw_processing 1.6 added later. Every release of bw2calc,
  bw_processing, matrix_utils and bw_graph_tools runs.
- The solvers run on one thread, so a timing does not depend on how many cores were free.
- The noise floor, measured with `just noise` on a pinned benchmark machine, at the ecoinvent
  size, on a slot of 8 efficiency cores:
  - asv, six quick runs per arm: bw2calc's first score under PyPardiso spreads 0.0% with ASLR
    on and 0.1% with it off (interquartile range over the median). ASLR changes nothing
    measurable for the asv cells, so it stays on.
  - CodSpeed, three runs with ASLR off through the real `setarch -R` (see below): the
    traversal cases are 0.035% and 0.014% apart, against 0.7 to 1.1% with the old shim that
    left ASLR on.
  - bw2data's write takes about 12.7 s wall time and 11.7 s CPU time. In either arm, 1 or 2
    samples in 12 stall for 16 to 17 s off the CPU (3 of 36 samples over two nights), at the
    same time as the host writes its disk cache back (blocked processes in `vmstat`). asv's
    median does not move, but max/min is no usable spread for this cell.

  At the smoke size a case varies by up to 4% (median 0.9%, 10 runs), apart from cases of a
  few milliseconds. So a step of 5% or more at the ecoinvent size is a real change. Short
  cases need the CPU on its performance power profile (on Linux, `powerprofilesctl set
  performance`): under a power-saving one, an idle core starts slow and they vary up to
  five-fold. `just noise` also writes each sample's CPU time, wall time and involuntary
  context switches to `rounds.jsonl`; `scripts/noise_summary.py` says how to read them.
  On a GitHub-hosted `ubuntu-latest` runner (the `noise-hosted` workflow, bw2calc, 10 runs,
  smoke size) the same cases vary by 1 to 14%, median 4.0% (2 to 6% for cases of 50 ms or
  more). A hosted runner would catch a several-fold step such as bw2calc 3.0.0 factorizing A,
  but a change below about 15% can hide in its spread.
- CodSpeed's runner turns address randomization (ASLR) off with `setarch -R`. Docker's
  default seccomp profile refuses that, so the CodSpeed box runs under
  [`docker/seccomp-noaslr.json`](../docker/seccomp-noaslr.json): Docker's default profile with one
  more rule, which allows only `personality(ADDR_NO_RANDOMIZE)` (`just seccomp-profile`
  rebuilds it).
- Each run records exactly what was installed (a `pylock.toml` lock file per environment)
  and an RO-Crate that names the code and settings that produced it.
