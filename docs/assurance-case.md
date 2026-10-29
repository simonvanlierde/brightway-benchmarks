# Assurance case

This page argues why brightway-benchmarks meets its security requirements, and names the code,
test or workflow behind each claim. [SECURITY.md](../.github/SECURITY.md) holds the scope, the
likely problems and how to report one; [CONTRIBUTING.md](../.github/CONTRIBUTING.md#how-it-fits-together)
describes the parts.

The requirements:

1. Code from a Brightway release or its dependencies must not change the host or the repository,
   apart from the result folders it is given.
2. A published timing must come with a result that matched an independent reference, or the case
   fails.
3. A pull request, a workflow input or a compromised dependency must not get write access to the
   repository, its releases or its Pages site.
4. The history pages and the release report must show only what was measured, and must not read
   or write outside their own folders.

## Threat model

We assume an attacker who controls:

- the code of a Brightway release or of a package it installs, which asv installs and runs;
- the files the benchmark box writes: results, asv's HTML, machine and version records;
- a pull request from a fork, its branch name and title;
- a new release of one of this project's own dependencies or GitHub Actions.

We do not defend against someone who can already run code on the host outside the box, or who
holds the maintainer's GitHub account. A bug in Brightway itself, Docker, asv or GitHub Actions is
reported upstream (SECURITY.md, "Scope").

## Trust boundaries

| Boundary | What crosses it | Controls |
| --- | --- | --- |
| The benchmark box | Brightway releases and their dependencies, installed by asv from PyPI or conda-forge | A throwaway container with the repository mounted read-only and only the result folders writable, every capability dropped, `no-new-privileges`, and limits on processes, memory and CPUs (`scripts/box.sh`); a new home folder on each run, and uv and pip read no config file, so a release cannot leave settings for the next run (`scripts/in-box.sh`); its package caches (uv, pip, rattler) and the generated datapackages stay in `.asv/` between runs; the stack each release runs on is pinned in `asv/<package>.stack.txt` |
| Hosted runners | Brightway releases in the macOS and Windows jobs of `compat` and in `codspeed`, which run outside the box | A throwaway GitHub-hosted runner with a read-only token; `codspeed` also holds an OIDC token for its upload, which cannot pass for `release.yml`: the check of a download names that workflow as the signer ([CONTRIBUTING.md](../.github/CONTRIBUTING.md#releasing)) |
| Box output to the host | `results/`, the asv HTML, `machine.json` and the version records | `just results-commit` copies only result records and no symlinks (`scripts/results-commit.sh`); the scripts that read box output (`site_index.py`, `compat_site.py`, `just stack`) refuse a symlink or a path that leaves their folder; the maintainer reads the results diff before pushing the `results` branch |
| Results to readers | The history pages and the release report | Every name and text the box wrote is HTML-escaped and URL-quoted before it goes into a page (`scripts/site_index.py`); `scripts/release_report.py` has an Atheris fuzz harness (`tests/fuzz_release_report.py`); the pages are static, built by the `site` workflow from `main` and the `results` branch |
| Correctness of a result | Scores computed by the release under test | `bwbench.check` compares each LCA score with a reference computed by the generator without an LU factorization, and fails the case outside the tolerance (`src/bwbench/__init__.py`); each run records the exact versions it installed |
| Pull requests and CI | Code and inputs from a fork | Workflows run on `pull_request`, never `pull_request_target` or `workflow_run`, so a fork gets a read-only token and no secrets; every workflow starts from `permissions: contents: read` and every checkout drops its credentials; manual inputs reach scripts through environment variables (`solvers-macos.yml`, `noise-hosted.yml`); zizmor and actionlint check the workflows on every pull request |
| Release and publishing | The source archive and the Pages site | `release` runs only on a `vX.Y.Z` tag of a commit on `main`, checks the tag against `pyproject.toml` and the CHANGELOG, and publishes `SHA256SUMS` and a signed build provenance attestation; tags are signed; Pages deploys only from `main` through the `github-pages` environment ([GOVERNANCE.md](../.github/GOVERNANCE.md#access)) |
| This project's dependencies | Python packages, the Docker base image, GitHub Actions | `uv.lock` pins the tree and CI installs with `uv sync --locked`; `uv audit` and dependency review check every pull request; Renovate waits 7 days before proposing a new release (30 for a major one); the base image and every action are pinned by digest or commit |

## Secure design principles

- **Least privilege.** Brightway's code runs only in the box, with no capabilities and a
  read-only repository. Workflows start from `contents: read`, and a job that needs more asks
  for it alone: `scorecard`, `codspeed`, `site` and `release`.
- **Fail-safe defaults.** A score outside the tolerance fails the case, so no timing is
  published without its check. A symlink in box output stops the script that meets it. The
  required checks must pass before a merge.
- **Complete mediation.** Every file that crosses from the box to the host goes through
  `results-commit.sh` or a script that checks the path, and every string in a page goes through
  `html.escape`.
- **Separation of privilege.** Measuring (the box), publishing results (the maintainer's push of
  `results`) and publishing pages (the `site` workflow) are separate steps.
- **Economy of mechanism.** One container script, `scripts/box.sh`, starts every box run, local
  or on the benchmark machine.
- **Open design.** Nothing relies on secret code or data: the generator, its seeds, the
  reference scores and the pinned stacks are public.

## Countering common weaknesses

- **Untrusted code execution (CWE-829, CWE-494).** Releases under test run only in the box;
  this project's own dependencies are locked, audited and pinned by digest or commit.
- **Link following and path traversal (CWE-59, CWE-22).** Box output is copied without symlinks,
  and the readers refuse a symlink or a path outside their folder.
- **Cross-site scripting (CWE-79).** Escaped names and text in the generated pages, which are
  static and need no account.
- **Injection in workflows (CWE-78, CWE-94).** No event text is expanded into a `run:` step;
  zizmor checks for template injection on every pull request.
- **Leaked credentials (CWE-798, CWE-522).** No stored secrets: the workflows use GitHub's
  short-lived token, and CodSpeed an OIDC token. Secret scanning with push protection and the
  betterleaks hook refuse a commit that holds a known secret.
- **Silent wrong results.** Not a CWE, but the failure that matters most for a benchmark: the
  reference check above, the seeded generator with a pinned golden hash, and the tests in
  `tests/`, which `main` requires.
