# Governance

brightway-benchmarks has one maintainer: Simon van Lierde
([@simonvanlierde](https://github.com/simonvanlierde)). This page says who decides what and who
can change the repository, the published results and the releases.

## How decisions are made

- The maintainer decides what goes in and what goes on the [roadmap](../ROADMAP.md), reviews and
  merges every pull request, triages issues, runs the published benchmarks, tags releases, and
  handles security reports as [SECURITY.md](SECURITY.md) says.
- Anyone can propose a change in an issue or a pull request, as
  [CONTRIBUTING.md](CONTRIBUTING.md) describes. The maintainer says yes, asks for changes, or says
  no with a reason, in the open on that issue or pull request.
- A finding that changes how a result should be read, such as a caveat on a database profile,
  gets its own issue, and [docs/findings.md](../docs/findings.md) links it.
- The maintainer enforces the [code of conduct](CODE_OF_CONDUCT.md).

## Access

- @simonvanlierde is the only account with access to the repository, as admin.
- `main` takes changes only through pull requests, with the `lint, types, tests` and `git hooks`
  checks passing. Force-pushes, deletion and merge commits are blocked. The `protect-main` ruleset
  asks for one approving review, which the admin may skip when merging, since there is no second
  reviewer.
- The `results` branch holds the published timings. Only the maintainer pushes it, with
  `just results-commit`, after reading the results diff.
- The history pages are published to GitHub Pages only by the `site` workflow, from `main`.
- Releases are made only by the `release` workflow, from a signed tag on `main`
  ([CONTRIBUTING.md](CONTRIBUTING.md#releasing)). Zenodo archives each release. The project is
  not published to PyPI.
- Renovate opens the dependency pull requests.

## If the maintainer is unavailable

A named person can take over the GitHub repository. The recovery details for Zenodo are in an
emergency-access vault.

The code, the results branch and the docs are public under the BSD 3-Clause license, so anyone can
fork the project and go on running it: `just bench` rebuilds every published number from the
release lists in `asv/` on any machine with Docker. The history pages stay online as they are
until someone publishes new results.

## Changes to this page

The maintainer changes this page through a normal pull request. A new maintainer is named here
first, with how they are added and how decisions are made among them.
