"""Read cells and select dependency stacks from asv result files."""

import hashlib
import itertools
import json
import math
import re
import sys
from collections.abc import Iterable, Iterator
from pathlib import Path

STACK = re.compile(r"-BWBENCH_STACK([0-9a-f]+)")
SHA = re.compile(r"[0-9a-f]{40}")

# Columns with one entry per parameter combination; the others hold one value per benchmark.
PER_CELL = {"result", "samples"}


def per_cell(column: str) -> bool:
    """Whether a result column holds one entry per parameter combination."""
    return column in PER_CELL or column.startswith("stats_")


def cells(row: list, columns: list[str]) -> dict[tuple, dict[str, object]]:
    """Each parameter combination's per-cell values, in asv's order (itertools.product).

    A column that is missing, shorter than the combinations or a single value (a case without
    parameters) gives None where it has no entry.
    """
    cell = dict(zip(columns, row, strict=False))

    def entry(column: str, i: int) -> object:
        values = cell.get(column)
        values = values if isinstance(values, list) else [values]
        return values[i] if i < len(values) else None

    combos = itertools.product(*(cell.get("params") or []))
    return {combo: {c: entry(c, i) for c in columns if per_cell(c)} for i, combo in enumerate(combos)}


def current_stack(subject: str) -> str:
    """The hash of asv/SUBJECT.stack.txt, as scripts/asv.sh puts it in environment names, or ""."""
    path = Path(f"asv/{subject}.stack.txt")
    return hashlib.sha256(path.read_bytes()).hexdigest()[:8] if path.exists() else ""


def pick(stacks: Iterable[str], current: str) -> str:
    """The current stack if it is among STACKS, else the lowest hash."""
    return min(stacks, key=lambda s: (s != current, s))


def current_rows(data: dict, benchmarks: dict) -> dict:
    """DATA without the cases whose recorded version differs from BENCHMARKS' (benchmarks.json).

    A new asv version means the benchmark changed (``GENERATOR_VERSION``), so its older times are
    a different measurement: asv's own publish drops them too. A row or benchmark with no version
    is kept.
    """
    columns = data.get("result_columns", [])
    at = columns.index("version") if "version" in columns else None
    if at is None:
        return data
    keep = {
        name: row
        for name, row in data["results"].items()
        if len(row) <= at
        or not isinstance(benchmarks.get(name), dict)
        or benchmarks[name].get("version") in (None, row[at])
    }
    return data | {"results": keep}


def result_files(folder: Path, benchmarks: dict) -> Iterator[tuple[Path, dict]]:
    """Result files in FOLDER, with rows from older benchmark versions filtered out."""
    for path in folder.glob("*/*-*.json"):
        yield path, current_rows(json.loads(path.read_text()), benchmarks)


def preferred_runs(folder: Path, info: dict) -> dict[tuple[str, str], list[dict]]:
    """(machine, commit) -> result files with each cell taken from its preferred stack.

    Only current cases count (``current_rows``), so a file with none is no candidate: a stack whose
    results are all of an older version never beats one that has current results.
    """
    current = current_stack(folder.name)
    found: dict[tuple[str, str], dict[str, dict[str, dict]]] = {}
    for path, data in result_files(folder, info):
        if not SHA.fullmatch(data["commit_hash"]):  # it becomes part of a report's path
            sys.exit(f"export_ui: {path}: commit_hash is not a full hash")
        if not data["results"]:
            continue
        stack = STACK.search(data["env_name"])
        env = found.setdefault((path.parent.name, data["commit_hash"]), {}).setdefault(
            STACK.sub("", data["env_name"]), {}
        )
        env[stack.group(1) if stack else ""] = data

    def ranked(stacks: dict[str, dict]) -> list[dict]:
        win = pick(stacks, current)
        return [stacks[s] for s in [win, *sorted(stacks.keys() - {win})]]

    return {
        key: [data for _, stacks in sorted(envs.items()) for data in fill_from_other_stacks(ranked(stacks))]
        for key, envs in found.items()
    }


def fill_from_other_stacks(files: list[dict]) -> list[dict]:
    """FILES of one environment and commit, winning stack first, each without the cells an earlier one has.

    A rerun of some cases on a new stack leaves the others on the older stacks only, so those come
    from there. A cell an earlier file has, even skipped or failed, is a NaN in the later ones.
    That includes the NaN `merge_results.merge_row` writes for a combination neither merged run
    timed, which a file cannot tell from a real skip: a later stack's value for it stays hidden.
    """
    held: set[tuple[str, tuple]] = set()
    out = []
    for data in files:
        columns = data.get("result_columns", ["result", "params"])
        at = columns.index("result")
        results, mine = {}, set()
        for name, row in data["results"].items():
            combos = list(cells(row, columns))
            mine |= {(name, c) for c in combos}
            taken = [(name, c) in held for c in combos]
            if combos and all(taken):
                continue
            if any(taken):
                row = list(row)  # noqa: PLW2901 - a copy, the file's own row stays as it is
                row[at] = [math.nan if t else v for t, v in zip(taken, row[at], strict=False)]
            results[name] = row
        held |= mine
        if results:
            out.append(data | {"results": results})
    return out
