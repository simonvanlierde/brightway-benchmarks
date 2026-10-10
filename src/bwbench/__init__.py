"""Continuous benchmarks for the Brightway LCA stack on seeded synthetic matrices.

Importing this package pins the BLAS and OpenMP thread pools to ``$BWBENCH_THREADS``
(default 1) before numpy loads, so timings do not depend on how many cores are free.
"""

import os

THREADS = os.environ.get("BWBENCH_THREADS", "1")
for _var in ("OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "OMP_NUM_THREADS"):
    os.environ[_var] = THREADS


def knob(name: str, default: str) -> list[str]:
    """A comma-separated benchmark parameter from ``$BWBENCH_<NAME>``.

    asv reads parameters at import, so a smoke run and a full run differ only in the
    environment: ``BWBENCH_SIZES=smoke`` here, ``ecoinvent,exiobase`` on a quiet machine.
    """
    return os.environ.get(f"BWBENCH_{name.upper()}", default).split(",")


def temporary_brightway_dir() -> str:
    """Point bw2data at a fresh directory, removed at exit. Call before importing bw2data."""
    import atexit  # noqa: PLC0415
    import shutil  # noqa: PLC0415
    import tempfile  # noqa: PLC0415

    path = tempfile.mkdtemp(prefix="bwbench-")
    atexit.register(shutil.rmtree, path, ignore_errors=True)
    os.environ["BRIGHTWAY2_DIR"] = path
    return path
