"""Time one catalogue case in this environment: the process ``bwbench compare`` starts per arm and round.

    PYTHONPATH=src:benchmarks python -m bwbench.timecase CASE PARAMS_JSON REPEATS

CASE is a benchmark's key in ``benchmarks/descriptions.toml``, such as
``bench_lca.SingleScore.time_first_score``, and PARAMS_JSON its parameters. The case runs once
untimed, then REPEATS times, each after a fresh setup and checked after the timing, as under
asv. ``$BWBENCH_HIDE`` names modules (comma-separated) to hide before Brightway imports them,
so bw2calc cannot pick that solver. Prints one JSON object: ``seconds`` (the timed calls),
``solver`` (what bw2calc used, or null), ``versions``, and ``missing`` (why the case does not
apply here, or null). Exits non-zero when the case fails or its check does.
"""

from __future__ import annotations

import contextlib
import json
import os
import sys
import time
from importlib import import_module, metadata
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bwbench.bench import Bench

BENCHMARKS = Path(__file__).resolve().parents[2] / "benchmarks"
VERSIONS = ("bw2calc", "bw2data", "numpy", "scipy", "pypardiso", "mkl", "scikit-umfpack")


def find(case: str) -> Bench:
    """The ``Bench`` behind a catalogue key: ``<module>.<asv class>.time_<name>``."""
    from bwbench.bench import benches  # noqa: PLC0415

    module, cls, method = case.split(".")
    paths = sorted(BENCHMARKS.glob(f"bench_*/{module}.py"))
    if len(paths) != 1:
        msg = f"{case}: {len(paths)} modules named {module} under {BENCHMARKS}"
        raise LookupError(msg)
    mod = import_module(f"{paths[0].parent.name}.{module}")
    for b in benches(vars(mod)):
        if f"time_{b.name}" == method and (b.asv or b.name.title().replace("_", "")) == cls:
            return b
    msg = f"{case}: no such benchmark in {paths[0]}"
    raise LookupError(msg)


def solver() -> str | None:
    """The direct solver bw2calc picked at import, or None when the case never imported it."""
    bc = sys.modules.get("bw2calc")
    if bc is None:
        return None
    return "pypardiso" if bc.PYPARDISO else "umfpack" if getattr(bc, "UMFPACK", False) else "superlu"


def versions() -> dict[str, str]:
    """Installed versions of the packages in ``VERSIONS``."""
    out = {}
    for dist in VERSIONS:
        with contextlib.suppress(metadata.PackageNotFoundError):
            out[dist] = metadata.version(dist)
    return out


def run(case: str, params: dict, repeats: int) -> dict:
    """Time CASE with PARAMS: one untimed call, then REPEATS timed ones."""
    import bwbench  # noqa: PLC0415 - pins the BLAS threads before numpy loads

    bwbench.point_pypardiso_at_mkl()
    seconds = []
    try:
        b = find(case)
        for i in range(repeats + 1):
            prepared = b.prepare(**params)
            try:
                t0 = time.perf_counter()
                result = prepared()
                elapsed = time.perf_counter() - t0
                prepared.verify(result)
            finally:
                prepared.teardown()
            if i:
                seconds.append(elapsed)
    except NotImplementedError as e:  # NotApplicable too: the case does not apply to this release or solver
        return {"seconds": [], "solver": solver(), "versions": versions(), "missing": str(e) or type(e).__name__}
    return {"seconds": seconds, "solver": solver(), "versions": versions(), "missing": None}


def main(argv: list[str]) -> None:
    """Hide what ``$BWBENCH_HIDE`` names, run the case and print the JSON object."""
    case, params, repeats = argv[0], json.loads(argv[1]), int(argv[2])
    # A None entry makes the import raise ModuleNotFoundError, as if the module were not installed.
    for name in filter(None, os.environ.get("BWBENCH_HIDE", "").split(",")):
        sys.modules[name] = None  # ty: ignore[invalid-assignment]
    print(json.dumps(run(case, params, repeats)))


if __name__ == "__main__":
    main(sys.argv[1:])
