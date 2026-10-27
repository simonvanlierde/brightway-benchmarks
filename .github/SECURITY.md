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

The project has no server, no accounts and no secrets of its own. The likely problems, and
what stops each:

- **A Brightway release or one of its dependencies runs harmful code.** asv installs every
  release it times, so that code runs only in the benchmark box: a throwaway container with
  the repository mounted read-only, every capability dropped, `no-new-privileges`, and
  limits on processes, memory and CPUs (`scripts/box.sh`).
- **A compromised dependency of this project.** `uv.lock` pins the tree, Renovate holds a
  new release back for 7 days, `uv audit` checks the lock on every pull request, and the
  Docker base image and every GitHub Action are pinned by digest or commit.
- **A workflow that leaks write access.** Every workflow starts with `permissions:
  contents: read`, no checkout keeps its credentials, no workflow runs on
  `pull_request_target`, and zizmor and actionlint check each workflow on every pull
  request. A job that needs more asks for it alone: `scorecard` uploads its report to code
  scanning, and the hand-started `site` workflow deploys GitHub Pages from `main`.
- **A wrong or tampered result.** Every benchmark checks its score against an independent
  reference and fails when it leaves the tolerance, and each run records the exact
  versions it installed.
- **A leaked secret.** The workflows use only GitHub's short-lived token, `.env` files are
  ignored, and secret scanning with push protection and the betterleaks hook refuse a
  commit that holds a known secret.
