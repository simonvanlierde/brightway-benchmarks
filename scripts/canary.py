#!/usr/bin/env python3
"""The node's nightly canary: a fixed workload, so a change in its time is the machine's, not Brightway's.

``canary.py run DIR`` times each workload (two warm-up calls, then 15 rounds, interleaved) and
writes ``DIR/<UTC time>.json``: the samples in seconds, their medians, the workloads' checksum,
the bwbench commit and the environment fingerprint. ``just canary`` runs it in the box, into
``results/canary/<machine>/``, which no Brightway history reads.

``canary.py check DIR`` compares the newest file with up to 14 before it that ran the same
workloads, and prints one line per workload, plus any fingerprint field that changed since the
night before. A workload moved when its median is further from the earlier nights' median than
3% or three times their median absolute deviation, whichever is larger. Fewer than 5 earlier
nights is too little history, and nothing moved.

Exit codes: 0 nothing moved, 1 a workload moved, 2 usage error or no canary file in DIR.

Never edit WORKLOADS or the functions they name: their source is hashed into every file, and
an edit starts a new history.
"""

import hashlib
import inspect
import json
import os
import statistics
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bwbench.fingerprint import fingerprint

ROUNDS, WARMUP = 15, 2
HISTORY, MINIMUM = 14, 5
FLOOR, SPREADS = 0.03, 3


def interpreter() -> int:
    """Pure-Python integer arithmetic and branches: one core's speed through the interpreter."""
    x, total = 1, 0
    for i in range(2_000_000):
        x = (x * 1103515245 + 12345) & 0x7FFFFFFF
        if x & 1:
            total += i
        else:
            total ^= x
    return total


def memory() -> int:
    """Sixteen copies of a 64 MiB buffer: memory bandwidth more than the core."""
    buffer = bytearray(range(256)) * (1 << 18)
    return sum(len(bytes(buffer)) for _ in range(16))


WORKLOADS = {"interpreter": interpreter, "memory": memory}


def workload_sha() -> str:
    """The checksum of the workloads' source: files with another one ran other code."""
    return hashlib.sha256("".join(inspect.getsource(f) for f in WORKLOADS.values()).encode()).hexdigest()


def run(folder: Path) -> Path:
    """Time the workloads and write one canary file into FOLDER; returns its path."""
    results = {name: f() for name, f in WORKLOADS.items()}  # also the first warm-up
    for _ in range(WARMUP - 1):
        for f in WORKLOADS.values():
            f()
    samples: dict[str, list[float]] = {name: [] for name in WORKLOADS}
    for _ in range(ROUNDS):
        for name, f in WORKLOADS.items():
            start = time.perf_counter_ns()
            f()
            samples[name].append((time.perf_counter_ns() - start) / 1e9)
    now = datetime.now(UTC)
    record = {
        "date": now.isoformat(timespec="seconds"),
        "commit": os.environ.get("BWBENCH_COMMIT") or "unknown",
        "workload_sha256": workload_sha(),
        "results": results,
        "samples": samples,
        "median": {name: statistics.median(s) for name, s in samples.items()},
        "fingerprint": fingerprint(),
    }
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{now:%Y%m%dT%H%M%SZ}.json"
    path.write_text(json.dumps(record, indent=1) + "\n")
    return path


def check(folder: Path) -> int:
    """Print how far the newest canary file is from the nights before it; 1 if a workload moved."""
    files = sorted(folder.glob("*.json"))
    if not files:
        print(f"canary: no canary file in {folder}", file=sys.stderr)
        return 2
    records = [json.loads(p.read_text()) for p in files]
    latest = records[-1]
    earlier = [r for r in records[:-1] if r["workload_sha256"] == latest["workload_sha256"]][-HISTORY:]
    print(f"canary: {files[-1].name} against {len(earlier)} earlier nights")
    if earlier:
        before = earlier[-1]["fingerprint"]
        for key, value in latest["fingerprint"].items():
            if before.get(key) != value:
                print(f"  fingerprint {key}: {before.get(key)} -> {value}")
    moved = False
    for name, value in latest["median"].items():
        past = [r["median"][name] for r in earlier if name in r["median"]]
        if len(past) < MINIMUM:
            print(f"  {name}: {value:.4f} s, too little history to judge")
            continue
        base = statistics.median(past)
        limit = max(FLOOR, SPREADS * statistics.median(abs(p / base - 1) for p in past))
        change = value / base - 1
        verdict = "MOVED" if abs(change) > limit else "steady"
        moved |= abs(change) > limit
        print(f"  {name}: {value:.4f} s, {change:+.1%} from {base:.4f} s (limit {limit:.1%}): {verdict}")
    return 1 if moved else 0


def main(argv: list[str]) -> int:
    """Run the subcommand in ARGV."""
    if len(argv) == 2 and argv[0] == "run":
        print(run(Path(argv[1])).as_posix())
        return 0
    if len(argv) == 2 and argv[0] == "check":
        return check(Path(argv[1]))
    print("usage: canary.py run DIR | check DIR", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
