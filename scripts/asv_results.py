"""Read cells and select dependency stacks from asv result files."""

import hashlib
import itertools
import json
import re
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
