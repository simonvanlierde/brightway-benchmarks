# Method

Results are in [findings.md](findings.md), how to run the benchmarks in
[running.md](running.md).

## What is measured

- bw2calc: one score; a second functional unit, with UMFPACK's refinement on and off; many
  functional units against three impact categories; Monte Carlo draws; `import bw2calc`. Each
  runs with the direct solvers (PyPardiso, UMFPACK, SuperLU) and the iterative ones.
  On BAFU 2025, a home-heating question too ([below](#the-home-heating-case)).
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
  process and consumers per product, one loop holding about two thirds of the products (64% in
  ecoinvent), negative waste inputs, its shares of inputs from the consumer's own location and
  sector, and a spectral radius of 0.78. `tests/test_measure.py` checks these on seeds 0 to 3,
  each within three standard deviations of its spread over seeds.
- `smoke`: the same structure at 200 products.
- `mc100k` and `regional`: 100,000 and 250,000 products.
- `exiobase` and `stress-random`: a random structure, a worst case for the solvers.

Only aggregate statistics of the ecoinvent database (ecoinvent Association) went into the
`ecoinvent` profile, no dataset or figure of one. They are in
[`src/bwbench/profiles/`](../src/bwbench/profiles).

Generator v5 groups regional variants into activity families that share supplier lists.
Family sizes and input counts use fixed quantiles, shuffled within size bands, so one large
family cannot dominate a seed. The calibrated profile passes the structural and fill guards
over seeds 0 to 3: mean METIS fill is 37.9, and SuperLU's COLAMD fill on Aᵀ is 27.9.
[Calibration choices and research](generator-calibration.md) explain the construction and its
limits. Input magnitudes still have a narrower upper tail than the real database.

The published synthetic histories in [findings.md](findings.md) use generator v4. Those times
retain its fill caveat until the v5 histories have been rerun. With a licence of your own,
[`scripts/solver_factorize.py`](../scripts/solver_factorize.py) times each
direct solver on the real matrix, and with `--cudss` NVIDIA's cuDSS on a GPU. That option
refactorizes unchanged values. `--cudss-updates` instead applies three deterministic row-scaled
value updates at fixed sparsity, checking every solution against SuperLU and its backward
error. It separates construction/initial transfer, analysis, update/transfer, factorization and
solve/return transfer. Value generation and CPU checks are outside those phase times; neither
option measures a complete Monte Carlo draw.

`just bw2io-import synthetic smoke,ecoinvent` times bw2io's ecoSpold2 import without a licence:
it writes a profile's system as ecoSpold2 files with bw2io's own `biosphere3` flows, so every
exchange links, and prints each step's time and peak memory. The files are as heavy as
ecoinvent 3.12's (137 KB a dataset) without changing the system's matrices: elementary exchanges,
properties, uncertainties and parameters come at the release's means per dataset, and comments at
its count and length per kind, since bw2io keeps their text in memory. ecoSpold2 allows one comment
per exchange, so datasets with few intermediate exchanges get fewer (7.1 a dataset against 12.8).
Review text, which bw2io skips, makes up the rest. With generator v4, the `ecoinvent` import peaked at 3.97 GB,
against 4.5 GB for the real release. `just bw2io-import RELEASE_FOLDER all` does the same on a
licensed release, read-only.

## The real databases

`BWBENCH_SIZES=useeio` runs the cases on USEEIO 1.1, the US EPA's input-output model: 388
commodities, 1,871 flows, and three of its impact categories (GCC, ACID, ETOX). It is
public domain, a US government work. It is the project archive that
`bw2io.install_project("USEEIO-1.1")` fetches from
[files.brightway.dev](https://files.brightway.dev/USEEIO-1.1.tar.gz), downloaded once into the
cache and checked against a pinned SHA-256 ([`src/bwbench/useeio.py`](../src/bwbench/useeio.py)).
The harness reads the matrices from the archive's processed datapackages and only renumbers their
ids, so the values are the model's own. Its reference scores come from a solve with no Brightway
code, like the synthetic ones. It is small, so it times a real structure with negative inputs and
duplicate exchanges, not the cost of a large factorization. Only timings are published, never scores.
It has no Monte Carlo case.

`BWBENCH_SIZES=bafu` runs them on BAFU 2025, cited as "Life Cycle Inventory database of the Swiss
Federal Administration, BAFU:2025": 11,747 processes, 2,678 flows, and three EN 15804+A2
categories (climate change, acidification, freshwater ecotoxicity). It is the archive that
`bw2io.install_project("BAFU-2025-v2")` fetches, read the same way
([`src/bwbench/bafu.py`](../src/bwbench/bafu.py)). At under half of ecoinvent's size, it times a
real LCI database's factorization. Its licence allows use in LCA studies but not distribution, so
the harness downloads it at run time and the repository, the results and the Zenodo dataset hold
only timings and aggregate statistics. Its matrix is badly conditioned (a condition number near
1e22), and its reference scores agree with a refined direct solve to about 2e-15. It has no Monte
Carlo case, although the archive carries uncertainty.

### The home-heating case

`bench_heating` asks a question a practitioner would: twenty years of heating a Dutch home with an
air-water heat pump or a condensing gas boiler. It runs only at `BWBENCH_SIZES=bafu`. A foreground
of six nodes sits on BAFU 2025 ([`src/bwbench/heating.py`](../src/bwbench/heating.py)): copies of
BAFU's Swiss heat pump and gas boiler, with Dutch gas, and electricity from a Dutch grid node that
mixes BAFU's Dutch grid with Dutch photovoltaics. The heat pump's electricity is replaced by
1/COP, not added to BAFU's own. The defaults are a seasonal COP of 3.0, 10,000 kWh of heat a year
and BAFU's Dutch grid as it is. The foreground is an in-memory bw_processing datapackage beside
BAFU's, so the bw2calc suite needs no bw2data. Four cases time it:

- `HeatingTimeline` (`bw_timex`): the complete per-heat inventory evenly distributed across twenty years, with an unchanged background.
  It checks the static score against an independent Neumann series on the matrices bw2data actually stores.
  Set `BWBENCH_TIMEX_SIZES=bafu` to include it.
- `HeatingTraversal` (`bw_graph_tools`): a supply-chain calculation budget of either two or one hundred per option.
- `HeatingMulti`: both options against the three EN 15804+A2 methods with `MultiLCA`.
- `HeatingSweep`: both options' climate change score over a square grid of COP (2.5 to 4.5) and
  renewable share (0 to 1). `rebuild` makes a new foreground and LCA per scenario. `redo_lci`
  factorizes the part no scenario changes once, and moves each scenario's electricity into the
  demand, which gives the same scores because the system is linear.

The defaults are illustrative assumptions. [Staffell et al. (2012)](https://doi.org/10.1039/C2EE22653G)
review heat pump performance across systems and climates; they do not establish a universal Dutch COP.
[CBS's January 2026 report](https://www.cbs.nl/nl-nl/longread/aanvullende-statistische-diensten/2026/de-energierekening-januari-2026?onepage=true)
reports gas consumption, not useful space heat, so it does not directly validate the heat-demand default.

The heating cases expand the archive's parent-compartment factors to otherwise uncharacterized
subcompartments. This follows Brightway's
[`match_subcategories`](https://docs.brightway.dev/en/latest/_modules/bw2io/strategies/lcia.html#match_subcategories)
convention. A flow must have exactly the same name and unit. Categories must descend from the
factor's category tuple; sibling compartments never match. An exact factor, including zero,
wins. Otherwise the most specific unique parent wins; ambiguous parents raise.
All three methods use this rule across the foreground and background. No numerical factor
is invented. The raw archive and the general BAFU benchmarks keep their original factors.

This matters for combustion: the archive's climate factors characterize the parent air compartment,
but the burner's fossil carbon dioxide, methane and nitrous oxide use its high-population
subcompartment. Without expansion, neither the original burner nor the copied burner has these
emissions characterized. The [heating story](../ui/src/pages/stories/home-heating.astro) publishes
corrected stage-level aggregate scores, with the FOEN citation and no inventory amounts.
These remain illustrative heating scenarios, not forecasts or household purchasing advice.

The reference is an independent Neumann series with no factorization. The bw2calc and traversal
cases use the expanded source factors and the foreground together. The bw_timex case uses the
matrices bw2data actually stores, accounting for its processing precision. Every native score must
match within `DIRECT_RTOL` (1e-9); an error outside that tolerance fails the case.

## How the results stay reproducible

- [asv](https://asv.readthedocs.io) runs every release of a package on one fixed set of
  dependencies, from before 2026-10-20, in `asv/<package>.stack.txt`. So a step in a graph is
  that package's own change. bw2calc 3.0.0 and later also get threadpoolctl.
- Each history starts at the oldest release that runs on that set: bw2data at 4.6 (peewee 4),
  bw_timex at 1.1.0. Every release of the other packages runs.
- Timings from the generator v5 rerun on run on Python 3.13; earlier times, including every
  published v4 history, ran on Python 3.12. Every release of every package installs and imports
  on 3.13 over the same pinned stacks.
- Each run records what was installed (`pylock.toml`) and an RO-Crate naming the code and
  settings.
- A change to the synthetic generator bumps `GENERATOR_VERSION`, which changes every
  benchmark's asv version, so each history starts again at the next run. The older times stay in
  the results branch's git history.
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
