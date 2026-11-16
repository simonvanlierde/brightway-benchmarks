# Task runner: https://just.systems. `just` lists the recipes, `just <name>` runs one.
#
# Each stack's recipes are in just/, prefixed (`py-`) because
# imports share one namespace, except the few only one kind has, such as `pipeline` or `up`.
import? 'just/python.just'

# List the recipes (what a bare `just` runs).
default:
    @just --list

# `just hooks` runs the git hooks, as the checks workflow does.
# What the python and ui workflows run, without the browser tests (`cd ui && pnpm run e2e`).
check:
    @just py-check
    @if just --show local-check >/dev/null 2>&1; then just local-check; fi

# Fix and format every stack here, as each stack's `fmt` recipe does.
fmt:
    @just py-fmt

# The checks workflow skips the hooks in its SKIP list, which the stack workflows run
# instead. Here they all run, so this can fail where the checks workflow passes.

# Run every git hook over the whole repo, not just staged files.
hooks:
    prek run -a

# The writer exits 1 whenever it changes a file, so the check that follows decides
# the result.

# Rewrite codemeta.json to agree with CITATION.cff, then check.
citation:
    -prek run citesync-write --hook-stage manual --all-files
    prek run citesync --all-files

# Release X.Y.Z. First run: cut CHANGELOG's [Unreleased] into [X.Y.Z] and commit it; merge that to main. Second run, on up-to-date main: sign and push tag vX.Y.Z.
release version:
    #!/usr/bin/env bash
    set -euo pipefail
    version={{ version }}
    [[ $version =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo "not a version: $version" >&2; exit 1; }
    tag=v$version
    repo=https://github.com/simonvanlierde/brightway-benchmarks
    # The release workflow refuses a tag that differs from pyproject.toml, after the tag exists.
    grep "^version = \"$version\"$" pyproject.toml >/dev/null ||
        { echo "set version = \"$version\" in pyproject.toml (and uv.lock) first" >&2; exit 1; }
    # citesync fails while the manifests and citation files disagree. Run it before any file changes.
    prek run citesync --all-files
    git fetch --quiet origin main
    # Not grep -q: it stops reading early, and under pipefail git show then fails on a
    # changelog bigger than the pipe buffer.
    if git show origin/main:CHANGELOG.md | grep "^## \[$version\] - " >/dev/null; then
        .github/scripts/tag-release.sh "$version"
        echo "Archive it in Software Heritage: https://archive.softwareheritage.org/save/ (git, $repo). The README badge then links to the SWHID."
        exit 0
    fi
    prev=$(sed -n 's/^## \[\([0-9][0-9.]*\)\].*/\1/p' CHANGELOG.md | head -1)
    if [ -n "$prev" ]; then link=$repo/compare/v$prev...$tag; else link=$repo/releases/tag/$tag; fi
    tmp=$(mktemp)
    trap 'rm -f "$tmp"' EXIT
    awk -v v="$version" -v d="$(date +%F)" -v repo="$repo" -v link="$link" '
        /^## \[Unreleased\]/ && !h { print; print ""; print "## [" v "] - " d; h = 1; next }
        /^\[Unreleased\]: / { print "[Unreleased]: " repo "/compare/v" v "...HEAD"; print "[" v "]: " link; l = 1; next }
        { print }
        END { if (!h) exit 1; if (!l) { print ""; print "[Unreleased]: " repo "/compare/v" v "...HEAD"; print "[" v "]: " link } }
    ' CHANGELOG.md >"$tmp" || { echo "CHANGELOG.md has no [Unreleased] section" >&2; exit 1; }
    # The same section the release workflow takes as notes; an empty one would publish none.
    awk -v head="## [$version]" '/^## \[/ { if (on) exit; on = index($0, head) == 1; next } on && NF' "$tmp" | grep . >/dev/null ||
        { echo "[Unreleased] has no entries to release" >&2; exit 1; }
    cp "$tmp" CHANGELOG.md
    git add CHANGELOG.md
    git commit -s -m "chore: release $version" -- CHANGELOG.md
    echo "Merge this commit to main, then run: just release $version"

# Protect the default branch (no deletion, no force-push, linear history, PRs squash-merged after the always-on checks pass and one approval) and the v* tags. Turn on secret scanning with push protection, private vulnerability reporting, CodeQL default setup and Dependabot alerts. Safe to rerun.
repo-settings:
    #!/usr/bin/env bash
    set -euo pipefail
    err=$(mktemp)
    trap 'rm -f "$err"' EXIT
    fail() {
        cat "$err" >&2
        grep -qE 'HTTP (403|404)' "$err" && echo "Rulesets on a private repo need a paid GitHub plan (or the repo does not exist, or you lack admin rights)." >&2
        grep -q 'must be part of the ruleset source' "$err" && echo "The main ruleset lets the Renovate app bypass the review, and GitHub accepts that only once the app is installed on this repo: add it at https://github.com/apps/renovate, then rerun." >&2
        exit 1
    }
    # Merge-method switches live on the repo itself; the ruleset also limits the PR button.
    gh api -X PATCH repos/{owner}/{repo} -F allow_squash_merge=true -F allow_merge_commit=false -F allow_rebase_merge=false -F delete_branch_on_merge=true -F web_commit_signoff_required=true >/dev/null 2>"$err" || fail
    # Push protection refuses a push that holds a known secret format, before it reaches the repo.
    # A private repo without Secret Protection refuses this, so it warns instead of failing.
    if gh api -X PATCH repos/{owner}/{repo} -f 'security_and_analysis[secret_scanning][status]=enabled' -f 'security_and_analysis[secret_scanning_push_protection][status]=enabled' >/dev/null 2>"$err"; then
        echo "Turned on secret scanning and push protection."
    else
        echo "Warning: secret scanning could not be turned on (a private repo needs Secret Protection): $(cat "$err")" >&2
    fi
    # Adopt an existing ruleset by name, else one with the same target that protects the same
    # refs as the file, updating it in place. The list has no conditions, so each candidate is read.
    for name in main main-checks tags; do
        file=.github/rulesets/$name.json
        case "$name" in
            main) want='["~DEFAULT_BRANCH"]' filter='.[] | select(.target == "branch" and (.name | test("checks?") | not)) | .id' ;;
            main-checks) want='["~DEFAULT_BRANCH"]' filter='.[] | select(.target == "branch" and (.name | test("checks?"))) | .id' ;;
            tags) want='["refs/tags/v*"]' filter='.[] | select(.target == "tag") | .id' ;;
        esac
        id=$(gh api "repos/{owner}/{repo}/rulesets?includes_parents=false" --jq "first(.[] | select(.name == \"$name\") | .id) // empty" 2>"$err") || fail
        if [ -z "$id" ]; then
            candidates=$(gh api "repos/{owner}/{repo}/rulesets?includes_parents=false" --jq "$filter" 2>"$err") || fail
            for candidate in $candidates; do
                same=$(gh api "repos/{owner}/{repo}/rulesets/$candidate" --jq ".conditions.ref_name.include == $want" 2>"$err") || fail
                if [ "$same" = true ]; then
                    id=$candidate
                    break
                fi
            done
        fi
        if [ -n "$id" ]; then
            gh api -X PUT "repos/{owner}/{repo}/rulesets/$id" --input "$file" >"$err" 2>&1 || fail
            echo "Updated ruleset '$name' ($id)."
        else
            # gh prints GitHub's reason for a refusal on stdout, so fail() needs both.
            gh api -X POST repos/{owner}/{repo}/rulesets --input "$file" >"$err" 2>&1 || fail
            echo "Created ruleset '$name'."
        fi
    done
    # SECURITY.md sends reports to a private security advisory, which this turns on.
    gh api -X PUT repos/{owner}/{repo}/private-vulnerability-reporting >/dev/null 2>"$err" || fail
    echo "Turned on private vulnerability reporting."
    # CodeQL default setup scans every PR and push to main.
    if gh api -X PATCH repos/{owner}/{repo}/code-scanning/default-setup -f state=configured >"$err" 2>&1; then
        echo "Turned on CodeQL default setup."
    else
        echo "Warning: CodeQL default setup could not be turned on, so code scanning stays off: $(cat "$err")" >&2
    fi
    # Dependabot alerts let Renovate open security PRs and turn on the dependency graph.
    gh api -X PUT repos/{owner}/{repo}/vulnerability-alerts >/dev/null 2>"$err" || fail
    echo "Turned on Dependabot alerts."
    echo "Zenodo: https://zenodo.org/account/settings/github/"
    if [ -f .github/first-release.md ]; then echo "First-release checklist: gh issue create --title 'First release' --body-file .github/first-release.md"; fi
# Set the GitHub About box from your answers: description and a topic per stack. Adds topics, never removes yours. Safe to rerun.
repo-about:
    gh repo edit --description 'Continuous benchmarks for the Brightway LCA stack on seeded synthetic matrices' --add-topic python

# A repo's own recipes that copier updates never touch. A `local-check` recipe there runs
# at the end of `just check`.
import? 'just/local.just'
