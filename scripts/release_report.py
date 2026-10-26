#!/usr/bin/env python3
"""Which cases pass, fail or skip per release: ``release_report.py SUBJECT``.

Reads .asv/stack/SUBJECT (``just stack-check``) and prints one row per release and
environment. asv records a failed case as null and a skipped one as NaN. A release with no
result file at all (the run stopped, or its environment never built) is listed as missing,
and the exit code is then 1.
"""

import json
import math
import subprocess
import sys
from pathlib import Path


def sha(mirror: Path, tag: str) -> str:
    """The commit a release tag points at, as the 8 characters asv names result files with."""
    run = subprocess.run(  # noqa: S603 - fixed git command on the asv mirror
        ["git", "--git-dir", str(mirror), "rev-parse", f"{tag}^{{commit}}"],  # noqa: S607
        capture_output=True,
        text=True,
        check=False,
    )
    return run.stdout.strip()[:8] or tag[:8]


def tally(text: str) -> tuple[str, str, int, int, int, list[str]]:
    """Count one asv result file: (commit, environment, ok, failed, skipped, failing cases).

    Raises:
        ValueError: ``text`` is not JSON.
        AttributeError, IndexError, KeyError, TypeError: the JSON does not have asv's shape.
    """
    data = json.loads(text)
    commit = data.get("commit_hash", "")[:8]
    ok = failed = skipped = 0
    broken = []
    for name, entry in data.get("results", {}).items():
        values = entry[0] if isinstance(entry[0], list) else [entry[0]]
        for v in values:
            if v is None:
                failed += 1
                broken.append(name.split(".", 1)[1])
            elif isinstance(v, float) and math.isnan(v):
                skipped += 1
            else:
                ok += 1
    return commit, data.get("env_name", ""), ok, failed, skipped, sorted(set(broken))


def main(subject: str) -> int:
    """Print the table for SUBJECT and return the exit code."""
    folder = Path(".asv/stack") / subject
    mirror = Path(".asv") / subject  # asv's clone of the upstream repository
    tags = Path(f"asv/{subject}.hashes").read_text().split()
    order = {sha(mirror, t): t for t in tags}
    rows = []
    for path in folder.rglob("*-*.json"):
        if path.name in {"machine.json", "benchmarks.json"}:
            continue
        commit, env, ok, failed, skipped, broken = tally(path.read_text())
        rows.append(
            (
                tags.index(order[commit]) if commit in order else -1,
                order.get(commit, commit),
                env,
                ok,
                failed,
                skipped,
                broken,
            )
        )
    print("| release | environment | ok | failed | skipped | failing cases |\n| --- | --- | --- | --- | --- | --- |")
    for _, tag, env, ok, failed, skipped, broken in sorted(rows):
        print(f"| {tag} | {env[-40:]} | {ok} | {failed} | {skipped} | {', '.join(broken)} |")
    missing = [t for t in tags if t not in {row[1] for row in rows}]
    for tag in missing:
        print(f"| {tag} | missing | | | | no result file |")
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
