#!/usr/bin/env python3
"""Fail when a smoke run left a null result, which is how asv records a failed benchmark.

Usage: check_smoke.py RESULTS_DIR (the .asv/smoke folder ``just smoke`` writes).
"""

import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
files = sorted(root.glob("*/smoke/*-*.json"))  # <commit>-<env>.json, not machine.json
failed = []
for f in files:
    for name, entry in json.loads(f.read_text()).get("results", {}).items():
        values = entry[0] if isinstance(entry[0], list) else [entry[0]]
        if any(v is None for v in values):
            failed.append(f"{f.relative_to(root)}: {name}")
print("\n".join(failed) or f"{len(files)} result files, no failed benchmark")
sys.exit(1 if failed or not files else 0)
