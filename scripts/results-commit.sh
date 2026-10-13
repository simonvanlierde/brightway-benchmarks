#!/usr/bin/env bash
# Commit results/ to the local `results` branch, the data the site is built from. Pushes nothing.
#
# The branch grows from the local branch, else from origin/results, else starts empty, so
# results from several machines or clones end up in one history. Files are added and
# updated, never deleted: another machine's folders stay. Only asv's JSON, the lock files
# and pip freezes are copied. It refuses results that name this host, because they become
# public once pushed: asv names a machine after the container hostname unless
# BWBENCH_MACHINE is set.
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

names=$(printf '%s\n' "$(hostname -s)" "$(hostname -f 2>/dev/null || true)" | sort -u | grep .)
if
    leaked=$(
        grep -rIlF -i -f <(echo "$names") results
        find results -iname "*$(hostname -s)*"
    )
    [ -n "$leaked" ]
then
    echo "results-commit: these name this host; rerun with BWBENCH_MACHINE set to a neutral label:" >&2
    echo "$leaked" | sort -u >&2
    exit 1
fi

tree=.asv/results-branch
git worktree prune
if git rev-parse -q --verify refs/heads/results >/dev/null; then
    git worktree add -q "$tree" results
elif git rev-parse -q --verify refs/remotes/origin/results >/dev/null; then
    git worktree add -q -b results "$tree" origin/results
else
    git worktree add -q --orphan -b results "$tree"
fi
trap 'git worktree remove --force "$tree"' EXIT

rsync -a --include '*/' --include '*.json' --include '*.toml' --include '*.txt' --exclude '*' results/ "$tree/"
git -C "$tree" add -A
if git -C "$tree" diff --cached --quiet; then
    echo "results-commit: nothing new"
    exit 0
fi
git -C "$tree" diff --cached --stat | tail -1
git -C "$tree" commit -q -m "results: $(date -u +%F) from $(git rev-parse --short HEAD)"
echo "Committed to the local results branch. To publish: git push origin results && gh workflow run site.yml"
