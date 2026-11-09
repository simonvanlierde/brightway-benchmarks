#!/usr/bin/env python3
"""The newest release of each minor line: ``minor_lines.py SUBJECT``.

Reads asv/SUBJECT.hashes and prints one entry per minor line (2.0.x, 2.1.x, ...), the last of
that line in file order, one per line and in file order. Entries are release tags, read as
versions offline (a leading ``v`` is ignored).

A bare commit is an untagged release or a fix not yet released, with no version to place it in a
line (bw_processing's is 1.3, bw2calc's 2.1.1), so it is always kept.
"""

import re
import sys
from pathlib import Path


def minor_lines(entries: list[str]) -> list[str]:
    """Entries to rerun; see the module docstring for the rule."""
    newest: dict[tuple[int, int] | str, str] = {}
    for entry in entries:
        match = re.fullmatch(r"v?(\d+)\.(\d+)(?:\.\d+)*", entry)
        newest[(int(match[1]), int(match[2])) if match else entry] = entry  # insertion order is file order
    return list(newest.values())


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    print("\n".join(minor_lines(Path(f"asv/{sys.argv[1]}.hashes").read_text().split())))
