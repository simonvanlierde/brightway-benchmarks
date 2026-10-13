"""Continuous benchmarks for the Brightway LCA stack on seeded synthetic matrices.

Importing this package pins the BLAS and OpenMP thread pools to ``$BWBENCH_THREADS``
(default 1) before numpy loads, so timings do not depend on how many cores are free.
"""

import os

THREADS = os.environ.get("BWBENCH_THREADS", "1")
for _var in ("OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "OMP_NUM_THREADS"):
    os.environ[_var] = THREADS

# Relative tolerances. Every generated matrix has a condition number of at most 3, so a
# real defect lands orders of magnitude above each of these.
DIRECT_RTOL = 1e-9  # direct solvers in float64 (measured: about 2e-16 to 4e-16)
ITERATIVE_RTOL = 1e-6  # bw2calc's iterative classes stop at a relative residual near 1e-8
# bw2data's processed arrays give about 3e-8 against the float64 reference
# (bw_processing #112 reports float32 amounts moving scores by about 1e-7).
BW2DATA_RTOL = 1e-6


def check(score: float, reference: float, rtol: float, what: str = "score") -> float:
    """Relative error of ``score`` against ``reference``; raises ``AssertionError`` above ``rtol``."""
    err = abs(score - reference) / abs(reference)
    if not err <= rtol:  # `not <=` also catches NaN
        msg = f"{what} {score!r} vs reference {reference!r}: relative error {err:.2e} > {rtol:.0e}"
        raise AssertionError(msg)
    return err


def check_table(scores: list[list[float]], references: list[list[float]], rtol: float, what: str = "score") -> float:
    """``check`` every ``scores[p][m]`` against ``references[p][m]``; returns the largest error."""
    if len(scores) != len(references):
        msg = f"{len(scores)} rows of scores against {len(references)} rows of references"
        raise AssertionError(msg)
    return max(
        check(score, ref, rtol, f"{what} [{p}][{m}]")
        for p, (row, ref_row) in enumerate(zip(scores, references, strict=True))
        for m, (score, ref) in enumerate(zip(row, ref_row, strict=True))
    )


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
