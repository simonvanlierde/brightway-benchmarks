# Contributing

Bug reports, questions about a result and pull requests are welcome. Report a vulnerability
as [SECURITY.md](SECURITY.md) says, not in a public issue.

## Report a bug or ask for a feature

Open an [issue](https://github.com/simonvanlierde/brightway-benchmarks/issues). For a bug,
say what you ran, what you expected and what happened. For a result that looks wrong, name
the package, release, case and database size, and the `just` command.

## Report a finding

Each `###` entry in [docs/findings.md](../docs/findings.md) says how to rerun it. It links
the case (for example [`bench_lca.SingleScore`](../benchmarks/bench_bw2calc/bench_lca.py)) or
the script in `scripts/`, or names the `just` recipe. A probe on licensed ecoinvent data still
links its script. Link the upstream issue, and link the finding back from that issue.
`tests/test_findings.py` fails on an entry without a rerun, or with a path or recipe that
doesn't exist.

## Set up

You need [uv](https://docs.astral.sh/uv/), [just](https://just.systems) and, for the
benchmarks themselves, Docker. Run `uv sync` once, and `prek install` to install the git
hooks with [prek](https://github.com/j178/prek). `just --list` shows every task, and the
[docs/running.md](../docs/running.md) explains the benchmark recipes.

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
- `ratios` runs `bwbench compare all` weekly on Linux, macOS and Windows runners, attests the
  result files and, on `main`, commits them to the `ratios` branch.
- `scorecard` rates the repository for the OpenSSF Scorecard badge.
- `codspeed` runs the pytest-codspeed suites under CodSpeed's CPU simulation on every push to
  `main` and on pull requests that touch them, and CodSpeed reports changes on the pull request.
- `release` runs on a pushed version tag (see Releasing).

`just smoke` builds the benchmark box and runs every benchmark once at the oldest and
latest release of its package. Run it when you change a benchmark, `scripts/` or
`docker/`.

## Tests

A change in behaviour comes with a test that fails without it, and a bug fix with a test
that reproduces the bug. The tests in `tests/` cover the database generator, the benchmark
helpers in `src/bwbench`, the shell scripts and the result tools.

A new benchmark case checks its result, as every case does: `bwbench.check` compares the
score with an independent reference score and fails the case when it leaves the tolerance. A
timing without a check is not accepted.

CI runs the tests with coverage and fails below 80% (`fail_under` in `pyproject.toml`);
`just py-cov` shows what is missing.

Fix a ruff or ty warning, or silence it on that line with the rule's name and a reason.

## Choosing dependencies

Add a dependency only when the standard library, NumPy, SciPy or a package already in
`pyproject.toml` cannot do the job. Prefer a maintained package with a compatible open
source license and wheels for Linux, macOS and Windows. Add it with `uv add`, so
`uv.lock` pins the whole tree, and CI installs from it with `uv sync --locked`.

Renovate ([`renovate.json5`](../renovate.json5)) proposes updates on Mondays, after a
release has been public for 7 days. `uv audit` checks every
locked dependency for known vulnerabilities on each pull request, and the `dependency
review` job in `checks` blocks a pull request that adds a vulnerable one.

The packages under test are not dependencies. Their releases are listed in
`asv/<package>.hashes`, and the dependencies they run on are fixed in
`asv/<package>.stack.txt`, which only a person moves ([docs/method.md](../docs/method.md#how-the-results-stay-reproducible)).

## Contribute a run

A result file of solver ratios from your own machine goes in `ratios/contributed/` by pull
request. [docs/running.md](../docs/running.md#contribute-a-run) has the steps, and the
`contributed` workflow checks the file.

## Commits and pull requests

`main` takes changes only through a pull request. Write commit subjects as
[Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/), such as
`fix(bw2calc): skip the adjoint case under umfpack-T`: imperative, lower case, no period.
The pull request title becomes the squash commit, so it follows the same rule. Both are
checked against [`committed.toml`](../committed.toml): a commit-msg hook (installed by
`prek install`) refuses a commit message that breaks the rule, and the `pull request title`
check fails a pull request whose title does. Add an entry to [CHANGELOG.md](../CHANGELOG.md)
under `[Unreleased]` for a change users see.

## Releasing

A release is one pull request and one tag:

1. In a pull request, set `version` in `pyproject.toml`, keep the project version in `uv.lock`
   in sync without changing dependency pins, and move the `[Unreleased]` entries in CHANGELOG.md
   under a new `## [X.Y.Z] - date` heading, with its compare link. Check that CITATION.cff and
   codemeta.json still describe the README and current viewer. `just release X.Y.Z` makes that CHANGELOG commit once `version` is set.
2. Review the full diff from the previous release tag. Run `just check`, the UI checks, unit and
   browser tests, `pnpm size` after its build, and `uv build`. Test the oldest and newest supported
   Python versions. Run the full mutation suite if the project defines one; a single-PR review
   does not replace the release review.
3. After the pull request is merged and its checks pass, run `just release X.Y.Z` again on an
   up-to-date `main`. It signs the tag on the merge commit and pushes it; the `release` workflow
   refuses a tag GitHub cannot verify.
4. After the release workflow succeeds, dispatch `site.yml` on `main` so the viewer’s build
   label picks up the tag. Verify the release downloads and deployed metadata.

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
adds the line, and the commit-msg hook refuses a commit without it.

To add it to commits you already made, run `git fetch origin`, then
`git rebase --signoff origin/main`. That works in a clone of this repository, where `origin`
is the only remote. If you work from a fork, use the remote that points at this repository
(often `upstream`) in place of `origin`. If you have not pushed the branch yet, that is all.
If you pushed it already, update it with `git push --force-with-lease`, which refuses to
overwrite work you have not seen. Do not use a plain `git push --force`.

The `dco` workflow checks every pull request from a fork and fails on a commit without the line. Pull requests from a branch in this repository skip it: pushing that branch already needed write access.

## How it fits together

- **A person** runs the `just` recipes on their own machine: `just bench`, `just smoke`,
  `just site`. The recipes start the benchmark box.
- **The benchmark box** (`scripts/box.sh`, `docker/Dockerfile`) is a throwaway container that
  installs each Brightway release from PyPI through asv and runs the cases in
  `benchmarks/`; the [assurance case](../docs/assurance-case.md#trust-boundaries) says what it
  may touch. Results come out as files in `results/`.
- **The generator** (`src/bwbench`) builds the seeded synthetic databases and the reference
  scores the cases are checked against.
- **`just results-commit`** copies `results/` to the `results` branch, and the `site`
  workflow builds the history pages from that branch and publishes them on GitHub Pages.
- **GitHub Actions** runs the checks above with a read-only token. `scorecard` may upload
  its report to code scanning, and `site` may deploy Pages, only from `main`. The `compat`
  archive job and the `ratios` publish job may push their data branches, only from `main`, and
  the `ratios` attest job may sign attestations. `release` may create a release, only for a
  pushed version tag. [Where it runs](../docs/architecture.md#where-it-runs) lists each tier and
  its token.

## Who maintains this

[GOVERNANCE.md](GOVERNANCE.md) names the maintainer, says how decisions are made and who has
access, and what happens if the maintainer is unavailable. Everyone taking part follows the
[code of conduct](CODE_OF_CONDUCT.md).
