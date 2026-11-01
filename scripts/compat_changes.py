#!/usr/bin/env python3
"""Report compatibility failures and recoveries between two published status snapshots.

Usage: compat_changes.py PREVIOUS CURRENT. A missing PREVIOUS starts a baseline; invalid
snapshots fail so a caller can keep its previous baseline rather than silently replace it.
"""

import json
import sys
from datetime import date
from pathlib import Path

FAILED = {"failure", "timed_out", "startup_failure", "action_required"}


def cells(status: dict) -> dict[tuple[str, str, str], str | None]:
    """Validate a published snapshot and index each unique job."""
    if (
        not isinstance(status, dict)
        or not isinstance(status.get("date"), str)
        or date.fromisoformat(status["date"]).isoformat() != status["date"]
        or not isinstance(status.get("run"), str)
        or not status["run"].strip()
        or not isinstance(status.get("cells"), list)
    ):
        msg = "snapshot needs an ISO date, a run link and a list of cells"
        raise ValueError(msg)
    indexed = {}
    for cell in status["cells"]:
        if not isinstance(cell, dict) or any(
            not isinstance(cell.get(field), str) or not cell[field].strip() for field in ("column", "python", "os")
        ):
            msg = "cell identity needs nonempty column, Python and operating system strings"
            raise ValueError(msg)
        key = (cell["column"], cell["python"], cell["os"])
        if key in indexed:
            msg = f"duplicate compatibility cell: {key}"
            raise ValueError(msg)
        if "today" not in cell or (
            cell["today"] is not None and (not isinstance(cell["today"], str) or not cell["today"].strip())
        ):
            msg = "cell conclusion must be a nonempty string or null"
            raise ValueError(msg)
        indexed[key] = cell["today"]
    return indexed


def report(previous: dict | None, current: dict) -> str:
    """Name failures, recoveries and jobs that were not evaluated, with both run links."""
    before = cells(previous) if previous is not None else {}
    after = cells(current)
    lines = [f"Compatibility {current['date']}: {current['run']}"]
    lines.append(
        f"Previous: {previous['run']}" if previous is not None else "No previous snapshot; starting a baseline."
    )
    for key, result in sorted(after.items()):
        old = before.get(key)
        name = f"{key[0]} · Python {key[1]} on {key[2]}"
        if result in FAILED:
            label = (
                "New failure" if old == "success" else "Still failing" if old in FAILED else "Failure, no prior result"
            )
        elif result == "success":
            if old not in FAILED:
                continue
            label = "Recovered"
        else:
            label = "Not evaluated"
        lines.append(f"- {label}: {name} ({old or 'unknown'} → {result})")
    lines.extend(
        f"- Absent from current run: {key[0]} · Python {key[1]} on {key[2]}"
        for key in sorted(before.keys() - after.keys())
    )
    return "\n".join(lines)


if __name__ == "__main__":
    prior, now = map(Path, sys.argv[1:])
    print(report(json.loads(prior.read_text()) if prior.exists() else None, json.loads(now.read_text())))
