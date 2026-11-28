"""Pair PyPardiso's default and explicit MKL lookup on one runner."""

import json
import os
import statistics
import sys
import time
from importlib.metadata import files, version
from pathlib import Path

from bwbench import THREADS


def runtime() -> Path:
    """Find the installed MKL runtime without timing the wheel lookup."""
    prefix, suffix = ("mkl_rt", ".dll") if sys.platform == "win32" else ("libmkl_rt.so", "")
    for entry in files("mkl") or ():
        if entry.name.startswith(prefix) and entry.name.endswith(suffix):
            path = entry.locate()
            if isinstance(path, Path) and path.is_file():
                return path.resolve()
    msg = "The mkl distribution has no runtime library"
    raise SystemExit(msg)


def main() -> None:
    """Time first scores and a second demand with a factorization already ready."""
    variable = "PYPARDISO_MKL_RT"
    os.environ.pop(variable, None)  # ensure the initial PyPardiso import uses default MKL lookup
    from pypardiso.scipy_aliases import pypardiso_solver  # noqa: PLC0415 - pin BLAS threads before importing PyPardiso

    from benchmarks.bench_bw2calc import bench_lca  # noqa: PLC0415 - pin BLAS threads before importing bw2calc

    if not bench_lca.bc.PYPARDISO:
        msg = "bw2calc did not load PyPardiso"
        raise SystemExit(msg)
    path = runtime()
    loaded = Path(pypardiso_solver.libmkl._name)  # noqa: SLF001 - ctypes exposes the loaded library here
    if not loaded.is_file() or not loaded.samefile(path):
        msg = f"Default MKL ({loaded.name}) differs from the wheel runtime ({path.name})"
        raise SystemExit(msg)
    samples: dict[str, dict[str, list[float]]] = {
        label: {"default": [], "explicit": []} for label in ("first_score", "second_demand")
    }
    for round_index in range(20):
        modes = ("default", "explicit") if round_index % 2 == 0 else ("explicit", "default")
        for mode in modes:
            if mode == "default":
                os.environ.pop(variable, None)
            else:
                os.environ[variable] = str(path)
            for label, case in (("first_score", bench_lca.first_score), ("second_demand", bench_lca.redo_lci)):
                prepared = case.prepare(size="smoke", cls="LCA")
                try:
                    start = time.perf_counter()
                    result = prepared()
                    samples[label][mode].append(time.perf_counter() - start)
                    prepared.verify(result)
                finally:
                    prepared.teardown()
    print(
        json.dumps(
            {
                "versions": {
                    package: version(package) for package in ("bw2calc", "pypardiso", "mkl", "numpy", "scipy")
                },
                "threads": THREADS,
                "runtime": path.name,
                "seconds": samples,
                "median_paired_ratio": {
                    label: statistics.median(d / e for d, e in zip(arms["default"], arms["explicit"], strict=True))
                    for label, arms in samples.items()
                },
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
