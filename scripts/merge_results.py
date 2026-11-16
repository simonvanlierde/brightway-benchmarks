"""Keep the cells a new run did not time: merge each changed asv result file with its version at HEAD.

asv writes a result file with only the parameter values of the run that wrote it, so a
smoke-size run of a commit would replace that commit's ecoinvent cells. Run in the results
branch worktree after `git add`: for each result file the commit changes, every cell the
run timed comes from the new file, and every other cell from HEAD. A benchmark whose
version changed keeps only the new cells, as its old ones timed other code.

A merged file's ``fingerprint`` is the new run's. Cells kept from HEAD may have run in another
environment (another kernel or lock, or before fingerprints existed), so when HEAD's
fingerprint differs from the new one, it goes into the top-level list ``kept_fingerprints``,
with ``null`` for cells from before fingerprints. HEAD's list and the new file's carry forward,
without duplicates and without the new fingerprint, and the list is left out when empty. It
says which environments the kept cells came from, not which cell came from which. A file whose
merged cells equal HEAD's stays as HEAD has it: the run timed nothing new.
"""

import hashlib
import itertools
import json
import math
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

# Columns with one entry per parameter combination; the others hold one value per benchmark.
PER_CELL = {"result", "samples"}


def per_cell(column: str) -> bool:
    """Whether a result column holds one entry per parameter combination."""
    return column in PER_CELL or column.startswith("stats_")


def cells(row: list, columns: list[str]) -> dict[tuple, dict[str, object]]:
    """Each parameter combination's per-cell values, in asv's order (itertools.product).

    The one decoder of an asv result row; scripts/release_changes.py reads its values and
    quartiles through it too. A column that is missing, shorter than the combinations or a
    single value (a case without parameters) gives None where it has no entry.
    """
    cell = dict(zip(columns, row, strict=False))

    def entry(column: str, i: int) -> object:
        values = cell.get(column)
        values = values if isinstance(values, list) else [values]
        return values[i] if i < len(values) else None

    combos = itertools.product(*(cell.get("params") or []))
    return {combo: {c: entry(c, i) for c in columns if per_cell(c)} for i, combo in enumerate(combos)}


def merge_row(old: list, new: list, columns: list[str]) -> list:
    """One benchmark's row: the union of both rows' parameter values, new cells first."""
    p, v = columns.index("params"), columns.index("version")
    if "started_at" in columns:
        started = columns.index("started_at")
        if (
            len(old) > started
            and len(new) > started
            and old[started] is not None
            and new[started] is not None
            and old[started] > new[started]
        ):
            old, new = new, old
    if len(old) <= p or len(new) <= p or len(old[p]) != len(new[p]) or old[v : v + 1] != new[v : v + 1]:
        return new
    axes = [n + [x for x in o if x not in n] for o, n in zip(old[p], new[p], strict=True)]
    if axes == new[p]:
        return new
    before, after = cells(old, columns), cells(new, columns)
    # A cell neither run timed is skipped, as asv writes it: NaN in result, None elsewhere.
    skipped = {"result": math.nan}
    merged = [after.get(combo) or before.get(combo) or skipped for combo in itertools.product(*axes)]
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
    if results == a["results"]:
        return old  # nothing new was timed, so HEAD's fingerprints still describe every cell
    # The new file may hold HEAD's cells itself (asv's --skip-existing-successful keeps them).
    kept = [*a.get("kept_fingerprints", []), *b.get("kept_fingerprints", [])]
    if a.get("fingerprint") != b.get("fingerprint"):
        kept.append(a.get("fingerprint"))
    unique = [fp for i, fp in enumerate(kept) if fp not in kept[:i] and fp != b.get("fingerprint")]
    if results == b["results"] and unique == b.get("kept_fingerprints", []):
        return new
    extra = {"kept_fingerprints": unique} if unique else {}
    return json.dumps(b | {"results": results, "durations": a.get("durations", {}) | b.get("durations", {})} | extra)


def git(tree: str, *args: str) -> str:
    """Git's output in the results worktree."""
    return subprocess.run(  # noqa: S603 - fixed git commands
        [shutil.which("git") or "git", "-C", tree, *args], check=True, capture_output=True, text=True
    ).stdout


def run_head(tree: Path, sha: str) -> str | None:
    """The commit and generator lines of the bwbench-run record that lists SHA, if one does."""
    for record in sorted(tree.rglob("bwbench-run-*.txt"), key=lambda p: p.name, reverse=True):
        lines = record.read_text().splitlines()
        if any(line[:64] == sha and line[64:66] == "  " for line in lines):
            return "".join(f"{line}\n" for line in lines if line.startswith(("commit ", "generator ")))
    return None


def main(tree: str) -> None:
    """Merge every changed result file in TREE with its version at HEAD, in place.

    run_crate.py credits a file by its checksum, so each merged file gets a run record in its
    folder that copies the run of the file it replaced. A file no record lists gets none.
    """
    changed = git(tree, "diff", "--cached", "--name-only", "--diff-filter=M", "-z", "--", "*.json").split("\0")
    records: dict[tuple[Path, str], list[str]] = {}  # (folder, run lines): checksum lines
    for path in filter(None, changed):
        new, old = git(tree, "show", f":{path}"), git(tree, "show", f"HEAD:{path}")
        merged = merge(old, new)
        if merged != new:
            Path(tree, path).write_text(merged)
            if merged != old:
                print(f"results-commit: kept earlier cells in {path}")
            head = run_head(Path(tree), hashlib.sha256(new.encode()).hexdigest())
            if head and merged != old:  # an unchanged file keeps the record that listed it
                sha = hashlib.sha256(merged.encode()).hexdigest()
                records.setdefault((Path(tree, path).parent, head), []).append(f"{sha}  {path}\n")
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    for (folder, head), lines in records.items():
        commit = head.partition("commit ")[2].split("\n", 1)[0][:12]
        (folder / f"bwbench-run-{stamp}-merge-{commit}.txt").write_text(head + "".join(lines))


if __name__ == "__main__":
    main(sys.argv[1])
