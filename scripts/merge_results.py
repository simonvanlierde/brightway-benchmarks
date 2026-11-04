"""Keep the cells a new run did not time: merge each changed asv result file with its version at HEAD.

asv writes a result file with only the parameter values of the run that wrote it, so a
smoke-size run of a commit would replace that commit's ecoinvent cells. Run in the results
branch worktree after `git add`: for each result file the commit changes, every cell the
run timed comes from the new file, and every other cell from HEAD. A benchmark whose
version changed keeps only the new cells, as its old ones timed other code.
"""

import itertools
import json
import shutil
import subprocess
import sys
from pathlib import Path

# Columns with one entry per parameter combination; the others hold one value per benchmark.
PER_CELL = {"result", "samples"}


def per_cell(column: str) -> bool:
    """Whether a result column holds one entry per parameter combination."""
    return column in PER_CELL or column.startswith("stats_")


def cells(row: list, columns: list[str]) -> dict[tuple, dict[str, object]]:
    """Each parameter combination's per-cell values, in asv's order (itertools.product)."""
    row = row + [None] * (len(columns) - len(row))
    combos = itertools.product(*row[columns.index("params")])
    return {
        combo: {c: (row[j] or [None] * (i + 1))[i] for j, c in enumerate(columns) if per_cell(c)}
        for i, combo in enumerate(combos)
    }


def merge_row(old: list, new: list, columns: list[str]) -> list:
    """One benchmark's row: the union of both rows' parameter values, new cells first."""
    p, v = columns.index("params"), columns.index("version")
    if len(old) <= p or len(new) <= p or len(old[p]) != len(new[p]) or old[v : v + 1] != new[v : v + 1]:
        return new
    axes = [n + [x for x in o if x not in n] for o, n in zip(old[p], new[p], strict=True)]
    if axes == new[p]:
        return new
    before, after = cells(old, columns), cells(new, columns)
    merged = [after.get(combo) or before.get(combo) or {} for combo in itertools.product(*axes)]
    row = new + [None] * (len(columns) - len(new))
    row[p] = axes
    for j, c in enumerate(columns):
        if per_cell(c):
            row[j] = [m.get(c) for m in merged] if any(c in m and m[c] is not None for m in merged) else None
    while row and row[-1] is None:  # asv leaves trailing empty columns out
        row.pop()
    return row


def merge(old: str, new: str) -> str:
    """The new file's text with the old file's cells merged in, or the new text unchanged."""
    a, b = json.loads(old), json.loads(new)
    columns = b.get("result_columns") if isinstance(b, dict) else None
    if not columns or "params" not in columns or a.get("result_columns") != columns:
        return new
    results = a["results"] | {
        name: merge_row(a["results"].get(name, []), row, columns) for name, row in b["results"].items()
    }
    if results == b["results"]:
        return new
    return json.dumps(b | {"results": results, "durations": a.get("durations", {}) | b.get("durations", {})})


def git(tree: str, *args: str) -> str:
    """Git's output in the results worktree."""
    return subprocess.run(  # noqa: S603 - fixed git commands
        [shutil.which("git") or "git", "-C", tree, *args], check=True, capture_output=True, text=True
    ).stdout


def main(tree: str) -> None:
    """Merge every changed result file in TREE with its version at HEAD, in place."""
    changed = git(tree, "diff", "--cached", "--name-only", "--diff-filter=M", "-z", "--", "*.json").split("\0")
    for path in filter(None, changed):
        new = git(tree, "show", f":{path}")
        merged = merge(git(tree, "show", f"HEAD:{path}"), new)
        if merged != new:
            Path(tree, path).write_text(merged)
            print(f"results-commit: kept earlier cells in {path}")


if __name__ == "__main__":
    main(sys.argv[1])
