#!/usr/bin/env python3
"""Energy per timed sample from a round log: ``energy_summary.py ROUNDLOG [--idle-w W]``.

A round log written with ``BWBENCH_ENERGY=1`` holds each sample's ``energy_j``: what the whole
CPU package used from the end of setup to teardown. For each case and environment this prints
the median joules per sample, the median joules above idle (``--idle-w`` watts times the
sample's wall time, subtracted), and the median watts. The counter sees every process on the
CPU, so the numbers mean something only on a quiet machine. Samples without energy are left out.
"""

import argparse
import json
from pathlib import Path
from statistics import median


def rows(log: Path, idle_w: float | None = None) -> list[tuple[str, str, int, float, float | None, float]]:
    """(case, environment, samples, median J, median J above idle or None, median W) per case."""
    groups: dict[tuple[str, str], list[dict]] = {}
    for line in log.read_text().splitlines():
        e = json.loads(line)
        if "energy_j" not in e:
            continue
        case = f"{e['case']}({e['params']})" if e["params"] else e["case"]
        groups.setdefault((case, e["env"]), []).append(e)
    out = []
    for (case, env), es in sorted(groups.items()):
        above = None if idle_w is None else median(e["energy_j"] - idle_w * e["wall"] for e in es)
        watts = median(e["energy_j"] / e["wall"] for e in es)
        out.append((case, env, len(es), median(e["energy_j"] for e in es), above, watts))
    return out


def main() -> None:
    """Print the table for the log named on the command line."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("log", type=Path)
    parser.add_argument("--idle-w", type=float, help="the package's idle draw in watts")
    args = parser.parse_args()
    print("| case | environment | samples | median J | median J above idle | median W |")
    print("| --- | --- | --- | --- | --- | --- |")
    for case, env, n, joules, above, watts in rows(args.log, args.idle_w):
        print(f"| {case} | {env} | {n} | {joules:.4g} | {'-' if above is None else f'{above:.4g}'} | {watts:.3g} |")


if __name__ == "__main__":
    main()
