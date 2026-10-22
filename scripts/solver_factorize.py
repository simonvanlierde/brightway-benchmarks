r"""Factorize and solve real ecoinvent's A with each direct solver bw2calc can use, one thread.

    docker run --rm --user "$(id -u):$(id -g)" -v "$PWD":/src:ro -v RELEASE_FOLDER:/ecoinvent:ro \
        -w /src IMAGE scripts/in-box.sh sh -c 'PYTHONPATH=src uv run -q --no-project --python 3.12 \
        --with bw2calc==3.1.0 --with threadpoolctl==3.7.0 --with pypardiso==0.4.7 \
        --with scikit-umfpack==0.4.2 --with pyklu==0.2.0 python scripts/solver_factorize.py [--pardiso]'

IMAGE is the box image ``scripts/box.sh`` builds, and RELEASE_FOLDER a licensed ecoinvent
release (its ``datasets/`` folder of ecospold2 files), mounted read-only. ``box.sh`` mounts
only this repo, hence the plain ``docker run``.

Builds A as ``scripts/measure_stats.py`` does, then times SuperLU and UMFPACK through
bw2calc's own ``spsolve`` and ``lu_solver``, KLU through pyklu, and with ``--pardiso``
PyPardiso: one factorization (median of 3) and one solve (median of 5) each. Checks every
solution's backward error and its score against UMFPACK's. Prints timings and fill only:
no dataset, name or amount.
"""

# First, so the BLAS thread pin lands before numpy loads (bwbench warns otherwise).
import bwbench  # noqa: F401, I001
import os
import statistics
import sys
import time
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor
from importlib.metadata import files, version
from pathlib import Path

import numpy as np
from scipy import sparse
from scipy.sparse.linalg import splu, spsolve

sys.path.insert(0, str(Path(__file__).parent))  # so the pool's workers can import read() by name
import measure_stats as ms

Solve = Callable[[np.ndarray], np.ndarray]


def build(folder: Path) -> sparse.csr_matrix:
    """Return the technosphere matrix A of the release in ``folder``, one column per dataset."""
    paths = sorted((folder / "datasets").glob("*.spold"))
    with ProcessPoolExecutor(max_workers=min(8, os.cpu_count() or 1)) as pool:
        records = list(pool.map(ms.read, paths, chunksize=200))
    index = {key: i for i, (key, *_) in enumerate(records)}
    rows, cols, data = [], [], []
    for j, (_key, ref, *_, inputs) in enumerate(records):
        rows.append(j), cols.append(j), data.append(ref)
        for supplier, amount in inputs:
            i = index.get(supplier)
            if i is not None:
                rows.append(i), cols.append(j), data.append(-amount)
    n = len(records)
    a = sparse.csr_matrix((np.array(data), (np.array(rows), np.array(cols))), shape=(n, n))
    a.sum_duplicates()
    a.sort_indices()
    return a


def timed[T](f: Callable[[], T], reps: int = 3) -> tuple[float, T]:
    """Return the median time of ``reps`` calls of ``f``, in seconds, and the last result."""
    times = []
    for _ in range(reps):
        t0 = time.perf_counter()
        out = f()
        times.append(time.perf_counter() - t0)
    return statistics.median(times), out


def main() -> None:
    """Time each solver on the release mounted at /ecoinvent and print the results."""
    import bw2calc.utils as bu  # noqa: PLC0415
    from PyKLU import Klu  # noqa: PLC0415

    a = build(Path("/ecoinvent"))
    n = a.shape[0]
    rng = np.random.default_rng(0)
    b = np.zeros(n)
    b[rng.choice(n, 30, replace=False)] = 1.0  # a sparse demand, like a few functional units
    print(
        f"ecoinvent in /ecoinvent: n {n}, nnz {a.nnz}; bw2calc {version('bw2calc')}, scipy {version('scipy')}"
        f", scikit-umfpack {version('scikit-umfpack')}, pyklu {version('pyklu')}",
        flush=True,
    )

    xs = {}
    c = rng.random(n)  # a positive characterization row, to compare scores

    def report(label: str, factor_s: float, solve: Solve, extra: str = "") -> None:
        solve_s, x = timed(lambda: solve(b), reps=5)
        xs[label] = x
        print(f"  {label:<34} factorize {factor_s:8.3f} s  solve {solve_s * 1e3:7.1f} ms {extra}", flush=True)

    # LCA.lci() without factorize: spsolve on CSR (SuperLU on A^T, transposed solve).
    s, x = timed(lambda: spsolve(a, b, use_umfpack=False))
    xs["SuperLU spsolve (LCA.lci)"] = x
    print(f"  {'SuperLU spsolve (LCA.lci)':<34} one score {s:8.3f} s", flush=True)

    bu.UMFPACK = False
    s, solve = timed(lambda: bu.lu_solver(a))
    lu = splu(a.T.tocsc())
    report("SuperLU lu_solver (A^T)", s, solve, f" nnz(L+U)/nnz(A) {(lu.L.nnz + lu.U.nnz) / a.nnz:.1f}")

    bu.UMFPACK = True
    s, solve = timed(lambda: bu.lu_solver(a))
    report("UMFPACK lu_solver (A^T)", s, solve)

    csc = a.tocsc()
    csc.sort_indices()
    s, k = timed(lambda: Klu(csc))
    report("KLU pyklu (A, AMD + BTF)", s, k.solve)

    if "--pardiso" in sys.argv:
        # pypardiso looks for MKL in sys.prefix only, which `uv run --with` puts elsewhere.
        mkl_rt = next(str(f.locate()) for f in files("mkl") or [] if f.name.startswith("libmkl_rt.so"))
        os.environ.setdefault("PYPARDISO_MKL_RT", mkl_rt)
        import pypardiso  # noqa: PLC0415

        def pardiso() -> pypardiso.PyPardisoSolver:
            p = pypardiso.PyPardisoSolver()
            p.factorize(a)
            return p

        s, p = timed(pardiso)
        report("PARDISO pypardiso (A)", s, lambda r: p.solve(a, r))

    # Backward error |Ax - b| / (|A| |x| + |b|) (inf norms), and the score's distance from UMFPACK's.
    norm_a = abs(a).sum(axis=1).max()
    ref = c @ xs["UMFPACK lu_solver (A^T)"]
    print("  accuracy (score = c.x, c random positive):", flush=True)
    for label, x in xs.items():
        backward = np.abs(a @ x - b).max() / (norm_a * np.abs(x).max() + np.abs(b).max())
        print(
            f"    {label:<34} backward error {backward:.1e}"
            f"  score rel. diff vs UMFPACK {abs(c @ x - ref) / abs(ref):.1e}  max|x| {np.abs(x).max():.1e}",
            flush=True,
        )


if __name__ == "__main__":
    main()
