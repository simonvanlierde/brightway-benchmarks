# Contributing

Bug reports, questions about a result and pull requests are welcome. Report a vulnerability
as [SECURITY.md](SECURITY.md) says, not in a public issue.

## Report a bug or ask for a feature

Open an [issue](https://github.com/simonvanlierde/brightway-benchmarks/issues). For a bug,
say what you ran, what you expected and what happened. For a result that looks wrong, name
the package, release, case and database size, and the `just` command.

## Set up

You need [uv](https://docs.astral.sh/uv/), [just](https://just.systems) and, for the
benchmarks themselves, Docker. Run `uv sync` once, and `prek install` to install the git
hooks with [prek](https://github.com/j178/prek). `just --list` shows every task, and the
README's [Running it](../README.md#running-it) explains the benchmark recipes.

## Checks

Run `just check` before you open a pull request. It runs what the `python` workflow runs:
ruff, the ruff format check, ty, pytest and `uv audit`. These run no Brightway code. `just hooks`
runs every git hook over the whole repository, as the `checks` workflow does: yamllint,
zizmor and actionlint on the workflows, rumdl on the Markdown. The betterleaks hook for
secrets runs only locally; on GitHub, secret scanning with push protection covers it.

Both workflows must pass before a pull request can merge. The others run apart from a pull
request:

- `fuzz` runs the Atheris harness of `scripts/release_report.py` for 60 seconds on a pull
  request that touches it.
- `smoke` runs `just smoke` weekly, and `compat` runs `just compat` nightly.
- `site` rebuilds the history pages daily after `compat`, and by hand after new results.
- `noise-hosted` and `solvers-macos` run by hand.
- `scorecard` rates the repository for the OpenSSF Scorecard badge.
- `codspeed` runs the pytest-codspeed suites under CodSpeed's CPU simulation on every push to
  `main` and on pull requests that touch them, and CodSpeed reports changes on the pull request.
- `release` runs on a pushed version tag (see Releasing).

`just smoke` builds the benchmark box and runs every benchmark once at the oldest and
latest release of its package. Run it when you change a benchmark, `scripts/` or
`docker/`. It runs Brightway's code only inside a throwaway container (`scripts/box.sh`).

## Tests

A change in behaviour comes with a test that fails without it, and a bug fix with a test
that reproduces the bug. The tests in `tests/` cover the database generator, the benchmark
helpers in `src/bwbench`, the shell scripts and the result tools.

A new benchmark case checks its result, as every case does: `bwbench.check` compares the
score with an independent reference score and fails the case when it leaves the tolerance. A
timing without a check is not accepted.

Fix a ruff or ty warning, or silence it on that line with the rule's name and a reason.

## Choosing dependencies

Add a dependency only when the standard library, NumPy, SciPy or a package already in
`pyproject.toml` cannot do the job. Prefer a maintained package with a compatible open
source license and wheels for Linux, macOS and Windows. Add it with `uv add`, so
`uv.lock` pins the whole tree, and CI installs from it with `uv sync --locked`.

Renovate ([`renovate.json5`](../renovate.json5)) proposes updates on Mondays, after a
release has been public for 7 days (30 days for a major one). `uv audit` checks every
locked dependency for known vulnerabilities on each pull request, and the `dependency
review` job in `checks` blocks a pull request that adds a vulnerable one.

The packages under test are not dependencies. Their releases are listed in
`asv/<package>.hashes`, and the dependencies they run on are fixed in
`asv/<package>.stack.txt`, which only a person moves (README, "How the results stay
reproducible").

## Commits and pull requests

`main` takes changes only through a pull request. Write commit subjects as
[Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/), such as
`fix(bw2calc): skip the adjoint case under umfpack-T`: imperative, lower case, no period.
The pull request title becomes the squash commit, so it follows the same rule. Add an
entry to [CHANGELOG.md](../CHANGELOG.md) under `[Unreleased]` for a change users see.

## Releasing

A release is one pull request and one tag:

1. In a pull request, set `version` in `pyproject.toml` and move the `[Unreleased]` entries
   in CHANGELOG.md under a new `## [X.Y.Z] - date` heading, with its compare link.
2. On the merge commit on `main`, make a signed tag and push it:
   `git tag -s vX.Y.Z -m vX.Y.Z && git push origin vX.Y.Z`.

The tag runs the `release` workflow. It checks the tag against `pyproject.toml` and the
CHANGELOG, then creates the GitHub release with that version's section as notes, the source
archive, `SHA256SUMS` and a signed build provenance attestation. Do not create the release by
hand. Zenodo archives each published release from `CITATION.cff`. To check a download:
`gh attestation verify brightway-benchmarks-X.Y.Z.tar.gz --repo simonvanlierde/brightway-benchmarks
--signer-workflow simonvanlierde/brightway-benchmarks/.github/workflows/release.yml`.

## Sign off your commits

Every commit in a pull request carries a `Signed-off-by:` line, which says you wrote the
change or have the right to submit it under the BSD 3-Clause license: the
[Developer Certificate of Origin 1.1](https://developercertificate.org/). `git commit -s`
adds the line. To add it to commits you already made, run
`git rebase --signoff upstream/main` (the branch you started from) and force-push the
branch.

The `dco` workflow checks every pull request from a fork and fails on a commit without the
line. Pull requests from a branch in this repository skip it: pushing that branch already
needed write access.

## How it fits together

- **A person** runs the `just` recipes on their own machine: `just bench`, `just smoke`,
  `just site`. The recipes start the benchmark box.
- **The benchmark box** (`scripts/box.sh`, `docker/Dockerfile`) is a throwaway container that
  installs each Brightway release from PyPI through asv and runs the cases in
  `benchmarks/`. It mounts the repository read-only, drops every capability and limits
  processes, memory and CPUs. Results come out as files in `results/`.
- **The generator** (`src/bwbench`) builds the seeded synthetic databases and the reference
  scores the cases are checked against.
- **`just results-commit`** copies `results/` to the `results` branch, and the `site`
  workflow builds the history pages from that branch and publishes them on GitHub Pages.
- **GitHub Actions** runs the checks above with a read-only token. `scorecard` may upload
  its report to code scanning, and `site` may deploy Pages, only from
  `main`, and `release` may create a release, only for a pushed version tag.

## Who maintains this

Simon van Lierde ([@simonvanlierde](https://github.com/simonvanlierde)) maintains
brightway-benchmarks: reviews and merges pull requests, runs the published benchmarks and
makes releases. He is the only person with write or admin access to the repository, its
settings and its GitHub Pages site. Anyone can propose a change by pull request. A new
maintainer is added by name in this section. If no maintainer can continue, the README says
so and the repository is archived; anyone may fork it under its license.
