# brightway-benchmarks

[![python](https://github.com/simonvanlierde/brightway-benchmarks/actions/workflows/python.yml/badge.svg)](https://github.com/simonvanlierde/brightway-benchmarks/actions/workflows/python.yml)
[![CodSpeed](https://img.shields.io/endpoint?url=https://codspeed.io/badge.json)](https://app.codspeed.io/simonvanlierde/brightway-benchmarks?utm_source=badge)
[![license](https://img.shields.io/badge/license-BSD--3--Clause-blue.svg)](LICENSE)
[![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/simonvanlierde/brightway-benchmarks/badge)](https://scorecard.dev/viewer/?uri=github.com/simonvanlierde/brightway-benchmarks)
[![OpenSSF Best Practices](https://www.bestpractices.dev/projects/15991/badge)](https://www.bestpractices.dev/projects/15991)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.23727602.svg)](https://doi.org/10.5281/zenodo.23727602)

How fast is [Brightway](https://docs.brightway.dev), and does it still give the right answer?
This repository times the calculations an LCA practitioner runs every day, across
Brightway's released versions: an LCI and LCIA, many functional units at once, Monte Carlo.
It also checks every result against an independent reference score. A release that makes a
calculation slower, or quietly changes a score, shows up here.

No licensed data is used. The benchmarks run on synthetic databases that copy the structure
of ecoinvent, so anyone can rerun them and the results can be published.

The history of every case is on the
[benchmark pages](https://simonvanlierde.com/brightway-benchmarks/).

## Results so far

All findings, with their numbers and upstream issues, are in [docs/findings.md](docs/findings.md).
Four that matter to most users:

- [The solver sets the time for one score.](docs/findings.md) On an ecoinvent-sized database,
  UMFPACK on OpenBLAS takes 2.63 s, PyPardiso 10.0 s and SciPy's SuperLU 27.7 s.
- [bw2calc 3.0.0 made `IterativeLCA` about 5 times slower with UMFPACK](docs/findings.md), and
  about 9 times with SuperLU. 3.1.0 fixed it.
- [bw2data 4.7 lost a 32% faster database write](docs/findings.md) that an earlier commit had
  added.
- [bw_timex 1.3.0 made the time-explicit LCI about 19 times slower.](docs/findings.md) 1.3.2
  fixed it, and 1.4.0 is faster again.

## Install a set that works

Each night the newest Brightway releases are installed together and every case runs once. The
site's [works together today](https://simonvanlierde.com/brightway-benchmarks/#works-together)
table links the last set that passed. Download its `requirements.txt` and use it as
constraints:

```sh
uv pip install brightway25 -c requirements.txt
```

## Run it yourself

You need Docker and [just](https://just.systems). Brightway's code runs only in a throwaway
container ([assurance case](docs/assurance-case.md)).

```sh
just smoke                                 # every package's oldest and latest release, small database
BWBENCH_SIZES=ecoinvent just bench bw2calc # every bw2calc release on the ecoinvent-sized database
just compat 3.13                           # today's releases together on Python 3.13
```

## More

- [Findings](docs/findings.md): what the histories show, for Brightway users and maintainers
- [Method](docs/method.md): what is measured, the synthetic databases, and how reproducible
  the results are
- [Running](docs/running.md): every recipe, the compat columns and the `BWBENCH_*` variables
- [CONTRIBUTING.md](.github/CONTRIBUTING.md): checks, tests and how to sign off commits
- [SECURITY.md](.github/SECURITY.md) and the [assurance case](docs/assurance-case.md)
- [GOVERNANCE.md](.github/GOVERNANCE.md), [ROADMAP.md](ROADMAP.md) and
  [CHANGELOG.md](CHANGELOG.md)
- [Code of conduct](.github/CODE_OF_CONDUCT.md) and [license](LICENSE)
