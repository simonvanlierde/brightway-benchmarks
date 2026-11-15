"""What the ratio-file fuzzing shares: a valid file, edits to it, and the contract a file must meet.

The Atheris harness (``fuzz_ratios.py``) and the Hypothesis test (``test_ratios_fuzz.py``) both use it.
"""

import contextlib
import copy
import io
import json
from pathlib import Path
from typing import Any

from bwbench import compare
from bwbench.fingerprint import fingerprint
from bwbench.ratios import bootstrap_interval, geometric_mean_ratio, ratio_seed

REL = "ratios/contributed/test-machine/2026-11-14.json"
# Values that sit on a boundary of what a file's fields accept.
SPECIALS = [
    None,
    True,
    0,
    1,
    -1,
    2**31,
    2**64,
    10**9,
    10**400,
    0.0,
    -0.0,
    1e-320,
    1e308,
    float("nan"),
    float("inf"),
    float("-inf"),
    "",
    "x" * 300,
    chr(0x202E),  # a bidi override
    "\x00",
    "2026-11-14",
    "ratios/contributed/x/2026-11-14.json",
    [],
    {},
    [[]],
    {"": {}},
]


def valid_doc() -> dict:
    """A contribution that passes ``problems`` and ``contribution_problems`` at ``REL``."""
    seconds = {"superlu": [1.0, 1.1, 0.9, 1.0], "umfpack": [0.5, 0.55, 0.45, 0.5], "pypardiso": [0.25, 0.3, 0.2, 0.25]}
    lock = {"name": "requirements.txt", "sha256": "0" * 64}
    seed, resamples = 4, 200

    def arm(name: str) -> dict:
        return {
            "installer": "uv",
            "python": "3.13",
            "requirements": ["bw2calc"],
            "solver": name,
            "versions": {"bw2calc": "2.0"},
            "fingerprint": fingerprint() | {"lock": lock},
            "seconds": seconds[name],
            "missing": None,
        }

    def ratio(name: str) -> dict:
        base, cand = seconds["superlu"], seconds[name]
        lo, hi = bootstrap_interval(base, cand, ratio_seed(seed, "solvers", name), resamples)
        r = geometric_mean_ratio(base, cand)
        return {
            "candidate": name,
            "ratio": r,
            "ci95": [lo, hi],
            "seconds": {"baseline": 1.0, "candidate": 0.5},
            "missing": None,
        }

    comparison = {
        "id": "solvers",
        "case": "bench_lca.SingleScore.time_first_score",
        "params": {"size": "smoke"},
        "baseline": "superlu",
        "arms": {name: arm(name) for name in seconds},
        "ratios": [ratio("umfpack"), ratio("pypardiso")],
    }
    return json.loads(
        json.dumps(
            {
                "format": "bwbench-ratios/1",
                "tier": "contributed",
                "machine": "test machine",
                "created": "2026-11-14T12:00:00Z",
                "source": {"commit": None, "run": None},
                "rounds": 4,
                "repeats": 3,
                "seed": seed,
                "resamples": resamples,
                "fingerprint": fingerprint(),
                "comparisons": [comparison],
            }
        )
    )


def slots(doc: object) -> list[tuple[Any, str | int]]:
    """Every place in DOC that holds a value, as (container, key)."""
    found: list[tuple[Any, str | int]] = []
    stack: list[Any] = [doc]
    while stack:
        node = stack.pop()
        pairs = node.items() if isinstance(node, dict) else enumerate(node) if isinstance(node, list) else ()
        for key, child in pairs:
            found.append((node, key))
            stack.append(child)
    return found


def edit(doc: dict, index: int, value: object, *, drop: bool = False) -> dict:
    """A copy of DOC with the INDEXth slot (modulo the slot count) set to VALUE, or removed with DROP."""
    out = copy.deepcopy(doc)
    container, key = slots(out)[index % len(slots(out))]
    if drop and isinstance(container, dict):
        del container[key]
    else:
        container[key] = value
    return out


def check(raw: bytes, folder: Path) -> None:
    """Hold ``bwbench validate --contribution`` to its contract on RAW as a file's bytes.

    It returns 0 or 1 and prints problems; nothing else escapes. The file sits at the one path
    ``contribution_problems`` accepts, so the content checks run too.
    """
    path = folder / REL
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    with contextlib.redirect_stderr(io.StringIO()):
        code = compare.validate([path], contribution=True)
    assert code in {0, 1}, code
