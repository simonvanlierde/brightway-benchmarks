#!/usr/bin/env bash
# Commit results/ to the local `results` branch, the data the site is built from. Pushes nothing.
#
# The branch grows from the local branch (fast-forwarded to origin/results when that is
# ahead), else from origin/results, else starts empty, so results from several machines or
# clones end up in one history. Files are added and updated, never deleted: another
# machine's folders stay. Only asv's JSON, the lock files and pip freezes are copied, and no
# symlinks. It refuses results that name this host, because they become public once pushed:
# asv names a machine after the container hostname unless BWBENCH_MACHINE is set. Other names
# to refuse (an ssh alias, say) go in BWBENCH_PRIVATE_NAMES, separated by spaces.
set -euo pipefail

[ -d results ] || {
    echo "results-commit: no results/ to commit" >&2
    exit 1
}
command -v rsync >/dev/null || {
    echo "results-commit: needs rsync" >&2
    exit 1
}
usage=$(git worktree add -h 2>&1 || true) # -h exits non-zero
grep -q -- --orphan <<<"$usage" || {
    echo "results-commit: needs git 2.42 or later" >&2
    exit 1
}

kept=(--include '*.json' --include '*.toml' --include '*.txt') # the files that get published

# Names of 4 characters or more, without generic ones a container may report.
names=$({
    hostname -s
    hostname -f 2>/dev/null || true
    tr ' ' '\n' <<<"${BWBENCH_PRIVATE_NAMES:-}"
} | grep -E '.{4,}' | grep -vixE 'localhost(\.localdomain)?' | sort -u || true)
if [ -n "$names" ]; then
    leaked=$(
        grep -rlaiF "${kept[@]}" -f <(echo "$names") results || true
        while read -r name; do find results -iname "*$name*"; done <<<"$names"
    )
    if [ -n "$leaked" ]; then
        echo "results-commit: these name this host; rerun with BWBENCH_MACHINE set to a neutral label:" >&2
        echo "$leaked" | sort -u >&2
        exit 1
    fi
fi

# A fresh folder outside the repo: code in the box can write to .asv/, and could plant a
# symlink there.
tree=$(mktemp -d)/results-branch
trap 'git worktree remove --force "$tree" 2>/dev/null; rm -rf "$(dirname "$tree")"' EXIT
git worktree prune
if git rev-parse -q --verify refs/heads/results >/dev/null; then
    git worktree add -q "$tree" results
    if git rev-parse -q --verify refs/remotes/origin/results >/dev/null &&
        ! git -C "$tree" merge -q --ff-only origin/results 2>/dev/null; then
        echo "results-commit: the local results branch and origin/results have diverged; merge them first" >&2
        exit 1
    fi
elif git rev-parse -q --verify refs/remotes/origin/results >/dev/null; then
    git worktree add -q -b results "$tree" origin/results
else
    git worktree add -q --orphan -b results "$tree"
fi

rsync -r -t --checksum --no-links --include '*/' "${kept[@]}" --exclude '*' results/ "$tree/"
git -C "$tree" add -A
if git -C "$tree" diff --cached --quiet; then
    echo "results-commit: nothing new"
    exit 0
fi
git -C "$tree" diff --cached --stat | tail -1
# --no-verify: the repo's hooks lint code, and this branch holds data only (no hook config).
git -C "$tree" commit -q --no-verify -m "results: $(date -u +%F) from $(git rev-parse --short HEAD)"
echo "Committed to the local results branch. To publish: git push origin results && gh workflow run site.yml"
