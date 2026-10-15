"""bw2calc's own ``lci()`` and ``lcia()`` with one sparse solver, on a synthetic system.

    PYTHONPATH=src uv run --no-project --with bw2calc==3.0.0 python scripts/solver_lci.py SOLVER [SIZE]

SOLVER is one of:

- ``superlu``, ``umfpack``, ``pypardiso``: bw2calc picks the solver itself. The faster
  ones are hidden from it, so ``superlu`` runs with scikit-umfpack and pypardiso installed.
- ``umfpack-T``: scikit-umfpack factorizing the CSR arrays as Aᵀ, patched into bw2calc.
- ``klu``: KLU through pyklu, patched into bw2calc.

SIZE is a profile name, ``ecoinvent`` by default. Prints the time of one score (a new
``LCA``, ``lci()``, ``lcia()``) and of ``lci(factorize=True)``, the median of 3 runs,
or one run when a run takes over a minute. Exits non-zero when a score is off by more
than ``DIRECT_RTOL``. Brightway runs only in the box (``just solver-lci``) or on a
hosted runner.
"""

# Hide what this solver must not see before bwbench, scipy or bw2calc import it.
# A None entry makes the import raise ModuleNotFoundError, as if it were not installed.
import os
import sys

SOLVER = sys.argv[1]
HIDE = {
    "superlu": ["pypardiso", "scikits.umfpack"],
    "umfpack": ["pypardiso"],
    "pypardiso": [],
    "umfpack-T": ["pypardiso"],
    "klu": ["pypardiso"],
}
if SOLVER not in HIDE:
    msg = f"unknown solver {SOLVER!r}; one of {', '.join(HIDE)}"
    raise SystemExit(msg)
sys.modules.update(dict.fromkeys(HIDE[SOLVER]))

if SOLVER == "pypardiso" and "PYPARDISO_MKL_RT" not in os.environ:
    # pypardiso looks for MKL in sys.prefix only, which `uv run --with` puts elsewhere.
    from importlib.metadata import PackageNotFoundError, files

    try:
        mkl_rt = [f.locate() for f in files("mkl") or [] if f.name.startswith("libmkl_rt.so")]
    except PackageNotFoundError:
        mkl_rt = []
    if mkl_rt:
        os.environ["PYPARDISO_MKL_RT"] = str(mkl_rt[0])

# First, so the BLAS thread pin lands before numpy loads (bwbench warns otherwise).
import bwbench  # noqa: E402, I001
import platform  # noqa: E402
import statistics  # noqa: E402
import time  # noqa: E402
import warnings  # noqa: E402
from collections.abc import Callable  # noqa: E402
from importlib.metadata import version  # noqa: E402
from pathlib import Path  # noqa: E402

import numpy as np  # noqa: E402
from scipy import sparse  # noqa: E402

from bwbench.synth import packages  # noqa: E402

warnings.simplefilter("ignore")  # bw2calc warns that a faster solver is missing; that is the point here


def umfpack_transposed(a: sparse.spmatrix) -> Callable[[np.ndarray], np.ndarray]:
    """Factorize A's CSR arrays, which are Aᵀ in CSC: less fill than A on LCA matrices."""
    import scikits.umfpack as um  # noqa: PLC0415

    m = sparse.csr_matrix(a)
    m.indices, m.indptr = m.indices.astype(np.int32), m.indptr.astype(np.int32)
    ctx = um.UmfpackContext("di")
    ctx.numeric(m)
    return lambda b: ctx.solve(um.UMFPACK_A, m, np.asarray(b, dtype=np.float64), autoTranspose=True)


def klu(a: sparse.spmatrix) -> Callable[[np.ndarray], np.ndarray]:
    """Factorize A with KLU, which splits it into blocks first (block triangular form)."""
    from PyKLU import Klu  # noqa: PLC0415

    m = sparse.csc_matrix(a)
    m.sort_indices()
    k = Klu(m)
    return lambda b: k.solve(np.asarray(b, dtype=np.float64))


def patch(bw2calc: object, factorized: Callable) -> None:
    """Route bw2calc's module-level ``spsolve`` and ``factorized`` through ``factorized``."""
    from bw2calc import lca_base  # noqa: PLC0415

    def spsolve(a: sparse.spmatrix, b: np.ndarray, *_: object, **__: object) -> np.ndarray:
        return factorized(a)(b)

    # lca_base binds both names at import; LCA.lci and decompose_technosphere use its copies.
    for module in (bw2calc, lca_base):
        module.spsolve, module.factorized = spsolve, factorized


def timed(run: Callable[[], float]) -> tuple[list[float], float]:
    """Run ``run`` 3 times, or once when it takes over a minute; the times and the last result."""
    times, out = [], 0.0
    while len(times) < 3 and (not times or times[0] < 60):
        t0 = time.perf_counter()
        out = run()
        times.append(time.perf_counter() - t0)
    return times, out


def main(size: str) -> None:
    """Time one score and lci(factorize=True) on profile ``size``, and check the scores."""
    import bw2calc  # noqa: PLC0415

    if SOLVER == "umfpack-T":
        patch(bw2calc, umfpack_transposed)
    elif SOLVER == "klu":
        patch(bw2calc, klu)
    picked = "pypardiso" if bw2calc.PYPARDISO else "umfpack" if bw2calc.UMFPACK else "superlu"
    if SOLVER in {"superlu", "umfpack", "pypardiso"} and picked != SOLVER:
        msg = f"bw2calc picked {picked}, not {SOLVER}: is {SOLVER} installed?"
        raise SystemExit(msg)

    inventory, methods, reference, _ = packages(size)
    ref = reference[0][0]

    def score(factorize: bool) -> float:  # noqa: FBT001
        lca = bw2calc.LCA(demand={0: 1}, data_objs=[inventory, methods[0]])
        lca.lci(factorize=factorize)
        lca.lcia()
        return lca.score

    try:
        from threadpoolctl import threadpool_info  # noqa: PLC0415

        blas = sorted({f"{p['internal_api']} {p['version']}" for p in threadpool_info()})
    except ImportError:
        blas = ["unknown"]
    print(
        f"{SOLVER} on {size}: bw2calc {version('bw2calc')}, scipy {version('scipy')},"
        f" {platform.system()} {platform.machine()}, BLAS {', '.join(blas)}",
        flush=True,
    )
    worst = 0.0
    for label, factorize in (("one score", False), ("lci(factorize=True)", True)):
        times, value = timed(lambda f=factorize: score(f))
        err = abs(value - ref) / abs(ref)
        worst = max(worst, err)
        print(
            f"  {label:<20} median {statistics.median(times):8.3f} s  runs {[round(t, 3) for t in times]}"
            f"  rel err {err:.1e}",
            flush=True,
        )
    maps = Path("/proc/self/maps")  # Linux: every BLAS loaded, also the one a C extension links
    if maps.exists():
        mapped = sorted({line.rsplit("/", 1)[-1] for line in maps.read_text().splitlines() if "blas" in line})
        print(f"  BLAS libraries mapped: {', '.join(mapped)}", flush=True)
    if worst > bwbench.DIRECT_RTOL:
        msg = f"score off by {worst:.1e}, more than {bwbench.DIRECT_RTOL:.0e}"
        raise SystemExit(msg)


if __name__ == "__main__":
    main(sys.argv[2] if len(sys.argv) > 2 else "ecoinvent")
