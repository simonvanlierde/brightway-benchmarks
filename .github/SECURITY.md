# Security

<!-- The advisories link below works only once Settings > Code security >
     Private vulnerability reporting is on. Turn it on when you create the repo. -->

## Report a vulnerability

Report it privately, through
[a GitHub security advisory](https://github.com/simonvanlierde/brightway-benchmarks/security/advisories/new)
or by email to <code@duinlab.nl>. Don't open a public issue or pull request for anything
exploitable: anyone can read those before there is a fix.

Please include what the problem is and where (a file, a workflow or a dependency), the steps
to reproduce it, and the impact you expect.

I acknowledge a report within 14 days, then tell you whether I can reproduce it and when I
expect a fix.

## Supported versions

Only the newest release gets fixes. A fix lands on `main` and goes out in the next release;
older releases are not patched. Upgrade by checking out the new tag and running `uv sync`.

## Fixes and disclosure

When a fix is on `main`, I publish the GitHub security advisory for it, with a CVE where one
applies, and credit you unless you'd rather not be named. The CHANGELOG entry for the fix
links the advisory.

## Scope

In scope:

- The code in this repository: the `bwbench` package, the benchmarks, the scripts and the
  benchmark box.
- The GitHub Actions workflows in `.github/workflows` and the history pages they publish.
- The dependencies in `uv.lock` and `asv/*.stack.txt`, when the problem affects this
  project.

Out of scope: a bug in Brightway itself (report it to that package), and a problem in a
dependency that does not affect this project.

## What could go wrong

[docs/assurance-case.md](../docs/assurance-case.md) argues these in full, with the trust
boundaries and the controls at each. The project has no server, no accounts and no secrets of its own. The likely problems, and
what stops each:

- **A Brightway release or one of its dependencies runs harmful code.** asv installs every
  release it times, so that code runs only in the benchmark box: a container with the
  repository mounted read-only, every capability dropped, `no-new-privileges`, and limits on
  processes, memory and CPUs (`scripts/box.sh`). The exceptions are the macOS and Windows
  jobs of the `compat` workflow and the `codspeed` workflow, which run on a throwaway
  GitHub-hosted runner with a read-only token. `codspeed` also holds an OIDC token for its
  upload, which cannot pass for `release.yml` (CONTRIBUTING.md names it in the verify step).
  The box's home folder is new on every run, and uv and pip read no config file, so a release
  cannot leave config for later runs. Its package caches (uv, pip, rattler) and the generated
  datapackages stay in `.asv/` between runs.
- **A compromised dependency of this project.** `uv.lock` pins the tree, Renovate holds a
  new release back for 7 days, `uv audit` checks the lock on every pull request, and the
  Docker base image and every GitHub Action are pinned by digest or commit.
- **A workflow that leaks write access.** Every workflow starts with `permissions:
  contents: read`, no checkout keeps its credentials, no workflow runs on
  `pull_request_target`, and zizmor and actionlint check each workflow on every pull
  request. A job that needs more asks for it alone: `scorecard` uploads its report to code
  scanning, `codspeed` uploads to CodSpeed, the `site` workflow deploys GitHub Pages
  from `main`, and `release` creates a release for a pushed version tag.
- **A wrong result.** Every LCA score is checked against an independent reference and fails
  when it leaves the tolerance, and each run records the exact versions it installed. The
  check runs in the same box as the release it times, so it cannot catch a release written
  to fool it: read the results diff before pushing the `results` branch. Host scripts that
  read what the box wrote (`site_index.py`, `just stack`) refuse to follow a symlink.
- **A leaked secret.** The workflows use only GitHub's short-lived token, `.env` files are
  ignored, and secret scanning with push protection and the betterleaks hook refuse a
  commit that holds a known secret.
