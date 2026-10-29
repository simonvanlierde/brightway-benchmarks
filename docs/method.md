# Method

What the benchmarks measure, the databases they run on, and how far you can trust a step in a
history. What the histories show is in [findings.md](findings.md). How to run them is in
[running.md](running.md).

## What is measured

| Package | What is timed, in LCA terms |
| --- | --- |
| bw2calc | One score (build the matrices, solve, characterize); a second functional unit on a solved system, also with UMFPACK's iterative refinement on and off; many functional units against three impact categories; Monte Carlo draws; a cold `import bw2calc` |
| bw2data | Writing a database, up to the size of ecoinvent; a cold `import bw2data` |
| bw_processing, matrix_utils | Building datapackages and matrices from many resource groups |
| bw_graph_tools | Supply-chain graph traversal, small and large |
| bw_timex | The time-explicit LCI as the timeline grows |

bw2calc runs each case with the direct solvers (PyPardiso, UMFPACK, SuperLU) and with its
iterative solvers. bw2calc's first score and bw2data's write also record peak memory.

### Every score is checked

Each LCA score is checked next to its timing, against a reference that uses no Brightway code
at all. So a fast but wrong release fails instead of looking good. Two kinds of case are
checked more loosely: Monte Carlo draws only for finite values, and bw_timex against bw2calc's
own score. The cases that only build datapackages, matrices or a graph traversal have no score
to check, and neither do the import cells.

## The synthetic databases

A database is generated from a seed, so the same settings give the same matrices on every
machine. No licensed data goes in. Its shape comes from a profile:

- `ecoinvent` has 26,533 products, like ecoinvent 3.12 cut-off. It copies that release's
  measured structure: how many inputs each process has, and how many consumers each product
  has. It has one large loop that holds 64% of the products, waste treatments with negative
  inputs, and units that span many orders of magnitude. Its spectral radius is 0.78, which
  sets how fast the supply-chain series converges.
- `smoke` is the same structure at 200 products, for quick checks.
- `mc100k` and `regional` scale it to 100,000 and 250,000 products, the sizes of a large
  Monte Carlo study and a regionalised database.
- `exiobase` and `stress-random` use a random structure, a worst case for the solvers.

Only aggregate statistics of ecoinvent went into the `ecoinvent` profile, calculated from the
ecoinvent database (ecoinvent Association). No dataset and no figure of a single dataset went
in. The statistics are in [`src/bwbench/profiles/`](../src/bwbench/profiles).

### Limits of the profile

A direct solver needs more memory and time for the `ecoinvent` profile than for the real
ecoinvent. SuperLU's factors hold 323 times as many entries as the matrix, against 175 for
ecoinvent. The likely cause: the real database's suppliers share more of their consumers. So
SuperLU times on this profile overstate real ecoinvent.
[#54](https://github.com/simonvanlierde/brightway-benchmarks/issues/54) tracks the work on it.

With a licence of your own,
[`scripts/solver_factorize.py`](../scripts/solver_factorize.py) times each direct solver on the
real ecoinvent matrix instead, and prints timings only.

## How the results stay reproducible

- [asv](https://asv.readthedocs.io) runs every release of a package on one fixed set of
  dependencies: those of its latest release, from before 2026-10-20, listed in
  `asv/<package>.stack.txt`. Only the package itself changes from one point in the history to
  the next, so a step in a graph is that package's change. One exception: bw2calc 3.0.0 and
  later need threadpoolctl, which its asv config installs beside the set. The older releases
  never import it.
- Each history starts at the oldest release that runs on that set. bw2data starts at 4.6, the
  first release on peewee 4, which older ones cannot import. bw_timex starts at 1.1.0, since
  1.0.0 fails a check that bw_processing 1.6 added later. Every release of bw2calc,
  bw_processing, matrix_utils and bw_graph_tools runs.
- The solvers run on one thread, so a timing doesn't depend on how many cores were free.
- Each run records exactly what was installed (a `pylock.toml` lock file per environment) and
  an RO-Crate that names the code and settings that produced it.
- CodSpeed's runner turns address randomization (ASLR) off with `setarch -R`, which Docker's
  default seccomp profile refuses. So the CodSpeed box runs under
  [`docker/seccomp-noaslr.json`](../docker/seccomp-noaslr.json): Docker's default profile plus
  one rule that allows only `personality(ADDR_NO_RANDOMIZE)`.

## The noise floor

A step in a history is a real change only if it is larger than the noise between runs. Here
the spread of a case is the interquartile range of its samples (the middle half) relative to
the median. `just noise` measures it ([running.md](running.md#measure-the-noise)).

On a pinned benchmark machine, on a slot of 8 efficiency cores:

| Where | Spread |
| --- | --- |
| asv, ecoinvent size, bw2calc's first score under PyPardiso, six runs | 0.0% with ASLR on, 0.1% with it off |
| CodSpeed, the traversal cases, three runs with ASLR off | 0.035% and 0.014%, against 0.7 to 1.1% with ASLR on |
| asv, smoke size, 10 runs | up to 4%, median 0.9% |

So a step of 5% or more at the ecoinvent size is a real change. ASLR changes nothing
measurable for the asv cases, so it stays on there. Cases of a few milliseconds vary more.

Short cases need the CPU on its performance power profile (on Linux,
`powerprofilesctl set performance`). Under a power-saving one, an idle core starts slow, and
they vary up to five-fold.

bw2data's write takes about 12.7 s wall time and 11.7 s CPU time. 1 or 2 samples in 12 stall
for 16 to 17 s off the CPU (3 of 36 samples over two nights), while the host writes its disk
cache back. asv's median doesn't move, but the slowest over the fastest sample is no usable
spread for this case.

### On a hosted runner

**A GitHub-hosted runner hides changes under about 15%.** On `ubuntu-latest` (the
`noise-hosted` workflow, bw2calc, 10 runs, smoke size), the same cases spread 1 to 14%, median
4.0%, and 2 to 6% for cases of 50 ms or more. A hosted runner would catch a several-fold step
such as bw2calc 3.0.0's, but not a small one.
