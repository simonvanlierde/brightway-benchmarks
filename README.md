# brightway-benchmarks

[![python](https://github.com/simonvanlierde/brightway-benchmarks/actions/workflows/python.yml/badge.svg)](https://github.com/simonvanlierde/brightway-benchmarks/actions/workflows/python.yml)
[![CodSpeed](https://img.shields.io/endpoint?url=https://codspeed.io/badge.json)](https://app.codspeed.io/simonvanlierde/brightway-benchmarks?utm_source=badge)
[![license](https://img.shields.io/badge/license-BSD--3--Clause-blue.svg)](LICENSE)
[![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/simonvanlierde/brightway-benchmarks/badge)](https://scorecard.dev/viewer/?uri=github.com/simonvanlierde/brightway-benchmarks)
[![OpenSSF Best Practices](https://www.bestpractices.dev/projects/15991/badge)](https://www.bestpractices.dev/projects/15991)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.23727602.svg)](https://doi.org/10.5281/zenodo.23727602)

How fast is [Brightway](https://docs.brightway.dev), and does it still give the right answer?
This repository times everyday LCA calculations across Brightway's releases: an LCI and LCIA,
many functional units at once, Monte Carlo. It checks every result against an independent
reference score, so a release that slows a calculation or changes a score shows up here.

The benchmarks run on synthetic databases that copy ecoinvent's structure, so anyone can rerun
them and the results can be published. One real database sits beside them: USEEIO 1.1 (US EPA,
public domain), downloaded from [files.brightway.dev](https://files.brightway.dev/USEEIO-1.1.tar.gz)
by a pinned SHA-256 when `BWBENCH_SIZES=useeio` asks for it.

Every case's history is on the
[benchmark pages](https://simonvanlierde.com/brightway-benchmarks/).

## Results so far

[Make your Brightway faster](docs/faster.md) says what to install or call. Four findings for
most users:

- [The solver sets the time for one score.](docs/findings.md#the-solver-sets-the-time-for-one-score) On an ecoinvent-sized database,
  UMFPACK on OpenBLAS takes 2.63 s, PyPardiso 10.0 s and SciPy's SuperLU 27.7 s.
- [bw2calc 3.0.0 made `IterativeLCA` about 5 times slower with UMFPACK](docs/findings.md#bw2calc-300-slowed-iterativelca-without-pypardiso-and-310-fixed-it), and
  about 9 times with SuperLU. 3.1.0 fixed it.
- [bw2data 4.7 lost a faster database write](docs/findings.md#bw2data-47-lost-the-faster-database-write): an earlier commit had
  cut its time by 32%.
- [bw_timex 1.3.0 made the time-explicit LCI about 19 times slower.](docs/findings.md#bw_timex-130-made-the-time-explicit-lci-about-19-times-slower) 1.3.2
  fixed it, and 1.4.0 is faster again.

## Install a set that works

Each night the newest Brightway releases are installed together and every case runs once. The
site's [works together today](https://simonvanlierde.com/brightway-benchmarks/#works-together)
table links the last set that passed; [docs/running.md](docs/running.md#install-a-set-that-works)
says how to install it.

## Run it yourself

You need Docker and [just](https://just.systems). Brightway's code runs in a throwaway
container, never on your machine ([assurance case](docs/assurance-case.md)).

```sh
just smoke                                 # every package's oldest and latest release, small database
BWBENCH_SIZES=ecoinvent just bench bw2calc # every bw2calc release on the ecoinvent-sized database
just compat 3.13                           # today's releases together on Python 3.13
```

## More

- [Findings](docs/findings.md): what the histories show
- [Method](docs/method.md): what is measured, the synthetic databases, the noise floor
- [Running](docs/running.md): every recipe, the compat columns and the `BWBENCH_*` variables
- [CONTRIBUTING.md](.github/CONTRIBUTING.md): checks, tests and how to sign off commits
- [SECURITY.md](.github/SECURITY.md) and the [assurance case](docs/assurance-case.md)
- [GOVERNANCE.md](.github/GOVERNANCE.md), [ROADMAP.md](ROADMAP.md) and
  [CHANGELOG.md](CHANGELOG.md)
- [Code of conduct](.github/CODE_OF_CONDUCT.md) and [license](LICENSE)
