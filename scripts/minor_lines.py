#!/usr/bin/env python3
"""The newest release of each minor line: ``minor_lines.py SUBJECT``.

Reads asv/SUBJECT.hashes and prints one entry per minor line (2.0.x, 2.1.x, ...), the last of
that line in file order, one per line and in file order. Entries are release tags, read as
versions offline (a leading ``v`` is ignored).

A bare commit has no version. It joins the line of the entry before it, since the file is in
release order, so it is kept only when no later release of that line follows it.
"""

import re
import sys
from pathlib import Path


def minor_lines(entries: list[str]) -> list[str]:
    """Entries to rerun; see the module docstring for the rule."""
    newest: dict[tuple[int, int] | None, str] = {}
    line = None
    for entry in entries:
        match = re.fullmatch(r"v?(\d+)\.(\d+)(?:\.\d+)*", entry)
        if match:
            line = (int(match[1]), int(match[2]))
        newest[line] = entry  # dicts keep first-insertion order, so lines stay in file order
    return list(newest.values())


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    print("\n".join(minor_lines(Path(f"asv/{sys.argv[1]}.hashes").read_text().split())))
