#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12,<3.14"
# dependencies = ["apache-otava==0.8.0"]
# ///
"""Apache Otava's change points in each series: ``uv run scripts/change_points.py < SERIES``.

Its dependencies are locked in change_points.py.lock (`uv lock --script`).
Reads a JSON list of series, each a list of positive values in time order, and writes one list
per series of ``{"index", "ratio", "pvalue"}``: the first value at the new level, the new level's
mean over the old one's, and the t-test's p-value. Otava pins its own numpy and scipy, so it runs
here, in an environment of its own, and export_ui.py stays on the standard library.
"""

import json
import sys

from otava.analysis import compute_change_points

MAX_PVALUE = 0.001  # Otava's default
WINDOW = 50  # Otava's default; a series here has tens of points, so one window holds it


def points(series: list[float], min_magnitude: float) -> list[dict]:
    """The change points in SERIES whose level moved by more than MIN_MAGNITUDE."""
    found, _ = compute_change_points(series, window_len=WINDOW, max_pvalue=MAX_PVALUE)
    out = []
    for cp in found:
        ratio = float(cp.stats.mean_2 / cp.stats.mean_1)
        # Otava keeps a step of any size when the values around it barely vary, so a 0.1%
        # step between two flat runs would count; the floor drops it.
        if abs(ratio - 1) > min_magnitude:
            out.append({"index": int(cp.index), "ratio": ratio, "pvalue": float(cp.stats.pvalue)})
    return out


if __name__ == "__main__":
    floor = float(sys.argv[1]) if len(sys.argv) > 1 else 0.0
    json.dump([points(s, floor) for s in json.load(sys.stdin)], sys.stdout)
