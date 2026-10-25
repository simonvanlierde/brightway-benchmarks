#!/usr/bin/env python3
"""Run-to-run noise from asv results with appended samples: ``noise_summary.py RESULTS_DIR``.

``just noise`` runs one commit several times with ``--append-samples``, so each case's
samples come from separate runs. For each case and environment this prints the number of
samples, the median, the spread between the 25th and 75th percentiles relative to the
median, and the slowest sample over the fastest. Cases whose timings vary by more than a
change we want to see need more samples, or a quieter machine.

If the folder holds ``rounds.jsonl`` (``BWBENCH_ROUNDLOG``), a second table gives each case's
lowest CPU time over wall time and most involuntary context switches per second, and counts
the samples that were preempted: in a CPU-bound case on one thread, a sample whose CPU time
is under ``PREEMPTED`` (95%) of its wall time spent the rest waiting for its core, so another
process slowed it, not the code. A case that waits on disk (bw2data's write) always counts
as preempted; read its context switches instead.
"""

import itertools
import json
import sys
from pathlib import Path

import numpy as np

PREEMPTED = 0.95  # CPU time / wall time below this marks a preempted sample


def rows(folder: Path) -> list[tuple[str, str, int, float, float, float]]:
    """(case, environment, samples, median s, IQR / median, max / min) per case."""
    out = []
    for path in sorted(folder.rglob("*-*.json")):
        if path.name in {"machine.json", "benchmarks.json"}:
            continue
        data = json.loads(path.read_text())
        columns = data.get("result_columns", [])
        if "samples" not in columns:
            continue
        env = data.get("env_name", path.stem)
        for name, entry in data.get("results", {}).items():
            if not name.split(".")[-1].startswith(("time_", "timeraw_")):
                continue
            params = entry[columns.index("params")] if "params" in columns else []
            labels = [", ".join(p) for p in itertools.product(*params)] if params else [""]
            i = columns.index("samples")
            per_param = (entry[i] if len(entry) > i else None) or []  # asv drops trailing empty columns
            for label, samples in zip(labels, per_param, strict=False):
                if not samples:
                    continue
                s = np.asarray(samples, dtype=np.float64)
                q25, med, q75 = np.quantile(s, [0.25, 0.5, 0.75])
                case = f"{name}({label})" if label else name
                out.append((case, env, s.size, float(med), float((q75 - q25) / med), float(s.max() / s.min())))
    return out


def usage_rows(log: Path) -> list[tuple[str, str, int, float, float, int]]:
    """(case, environment, samples, lowest CPU / wall, most involuntary switches per s, preempted) per case."""
    groups: dict[tuple[str, str], list[dict]] = {}
    for line in log.read_text().splitlines():
        e = json.loads(line)
        case = f"{e['case']}({e['params']})" if e["params"] else e["case"]
        groups.setdefault((case, e["env"]), []).append(e)
    out = []
    for (case, env), es in sorted(groups.items()):
        ratios = [e["cpu"] / e["wall"] for e in es]
        rates = [e["nivcsw"] / e["wall"] for e in es]
        out.append((case, env, len(es), min(ratios), max(rates), sum(r < PREEMPTED for r in ratios)))
    return out


def main() -> None:
    """Print the table for the folder named on the command line."""
    table = rows(Path(sys.argv[1]))
    print("| case | environment | samples | median | IQR / median | max / min |\n| --- | --- | --- | --- | --- | --- |")
    for case, env, n, med, iqr, spread in table:
        print(f"| {case} | {env} | {n} | {med:.4g} s | {iqr:.1%} | {spread:.2f} |")
    log = Path(sys.argv[1]) / "rounds.jsonl"
    if log.exists():
        print(f"\n| case | environment | samples | lowest CPU / wall | most switches / s | preempted (< {PREEMPTED}) |")
        print("| --- | --- | --- | --- | --- | --- |")
        for case, env, n, low, most, preempted in usage_rows(log):
            print(f"| {case} | {env} | {n} | {low:.3f} | {most:.0f} | {preempted} |")


if __name__ == "__main__":
    main()
