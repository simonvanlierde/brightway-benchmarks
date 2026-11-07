#!/usr/bin/env python3
"""Sample idle CPU package power for five minutes; run under the machine's quiet gate."""

import json
import os
import sys
import time
from pathlib import Path


def sample(rapl: Path, seconds: int = 300, interval: int = 5) -> dict:
    """Sum short RAPL deltas so a long baseline can cross multiple counter wraps."""
    counter = rapl / "energy_uj"
    span = int((rapl / "max_energy_range_uj").read_text())
    previous = int(counter.read_text())
    start = last = time.monotonic()
    joules = 0.0
    watts = []
    while last - start < seconds:
        time.sleep(interval)
        now = time.monotonic()
        # A stalled sampler cannot tell how many times the counter wrapped.
        if now - last > 60:
            msg = "RAPL sampling paused for over 60 seconds; discard this baseline"
            raise RuntimeError(msg)
        current = int(counter.read_text())
        delta = (current - previous) % span / 1e6
        joules += delta
        watts.append(delta / (now - last))
        previous, last = current, now
    return {"idle_w": joules / (last - start), "joules": joules, "seconds": last - start, "watts": watts}


if __name__ == "__main__":
    result = sample(Path(os.environ.get("BWBENCH_RAPL", "/sys/class/powercap/intel-rapl:0")))
    Path(sys.argv[1]).write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result))
