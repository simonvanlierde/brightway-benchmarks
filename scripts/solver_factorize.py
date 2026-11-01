r"""Factorize and solve real ecoinvent's A with each direct solver bw2calc can use, one thread.

    docker run --rm --user "$(id -u):$(id -g)" -v "$PWD":/src:ro -v RELEASE_FOLDER:/ecoinvent:ro \
        -w /src IMAGE scripts/in-box.sh sh -c 'PYTHONPATH=src uv run -q --no-project --python 3.12 \
        --with bw2calc==3.1.0 --with threadpoolctl==3.7.0 --with pypardiso==0.4.7 \
        --with scikit-umfpack==0.4.2 --with pyklu==0.2.0 python scripts/solver_factorize.py [--pardiso] [--cudss]'

IMAGE is the box image ``scripts/box.sh`` builds, and RELEASE_FOLDER a licensed ecoinvent
release (its ``datasets/`` folder of ecospold2 files), mounted read-only. ``box.sh`` mounts
only this repo, hence the plain ``docker run``.

Builds A as ``scripts/measure_stats.py`` does, then times SuperLU and UMFPACK through
bw2calc's own ``spsolve`` and ``lu_solver``, KLU through pyklu if installed, and with ``--pardiso``
PyPardiso: one factorization (median of 3) and one solve (median of 5) each; PyPardiso
also a refactorization that reuses its analysis. Checks every
solution's backward error and its score against UMFPACK's. Prints timings and fill only:
no dataset, name or amount, plus which BLAS is loaded.

To time conda-forge's builds, run the script with the python of an asv ``rattler`` environment
(``.asv/env/bw2calc-conda/*/bin/python``, which has no pyklu) in place of ``uv run``, still
with ``PYTHONPATH=src``.

``--cudss`` adds NVIDIA's cuDSS on the GPU (add ``--gpus all`` to ``docker run``): plan and
factorize, then refactorize the same values with the plan reused. This is not a Monte Carlo draw. It needs
``nvmath-python[cu12]==1.0.0`` and ``nvidia-cudss-cu12==0.8.0.10`` in a real venv (``uv venv``
plus ``uv pip install``, then that venv's python): under ``uv run --with``, nvmath cannot find
the CUDA libraries. ``--cudss-updates`` instead measures three deterministic row-rescaled
value updates, with a new independent SuperLU reference for each. Construction/initial transfer,
analysis, update/transfer, numeric factorization and solve/return transfer are separate wall times.
CPU validation and value generation are excluded; no complete LCA draw is measured.
"""

# First, so the BLAS thread pin lands before numpy loads (bwbench warns otherwise).
import bwbench  # noqa: I001
import os
import statistics
import sys
import time
from collections.abc import Callable, Iterable, Iterator
from concurrent.futures import ProcessPoolExecutor
from contextlib import ExitStack
from dataclasses import dataclass
from functools import partial
from importlib.metadata import version
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


def warm_cudss() -> None:
    """Initialize the CUDA context before recording GPU phase timings."""
    import nvmath.sparse.advanced as sa  # noqa: PLC0415

    with ExitStack() as resources:
        solver = sa.DirectSolver(sparse.identity(100, format="csr"), np.ones(100))
        resources.callback(solver.free)
        solver.plan()
        solver.factorize()


def time_cudss(a: sparse.csr_matrix, b: np.ndarray, *, resources: ExitStack | None = None) -> tuple[float, Solve, str]:
    """Time initial cuDSS setup and unchanged-value refactorization, including host transfers.

    The returned solve retains one solver; ``resources`` releases it after its last use.
    """
    import nvmath.sparse.advanced as sa  # noqa: PLC0415

    warm_cudss()
    retained = None
    times = []
    try:
        for _ in range(3):
            if retained is not None:
                retained.free()
                retained = None
            start = time.perf_counter()
            retained = sa.DirectSolver(a, b)
            retained.plan()
            retained.factorize()
            times.append(time.perf_counter() - start)
        solver = retained
        seconds = statistics.median(times)
        again, _ = timed(lambda: (solver.reset_operands(a=a.copy()), solver.factorize()))
    except BaseException:
        if retained is not None:
            retained.free()
        raise
    if resources is not None:
        resources.callback(solver.free)
    return seconds, lambda r: (solver.reset_operands(b=r), solver.solve())[1], f" unchanged refactorize {again:.3f} s"


@dataclass(frozen=True)
class CudssUpdate:
    """One completed and checked update; all phase times are wall-clock seconds."""

    replanned: bool
    setup_s: float
    analysis_s: float
    update_s: float
    factorize_s: float
    solve_s: float
    relative_error: float
    backward_error: float


def value_updates(a: sparse.csr_matrix, count: int = 3) -> Iterator[sparse.csr_matrix]:
    """Yield deterministic row-rescaled matrices, preserving sparsity and invertibility.

    This controlled numerical update is not an LCA uncertainty sample.
    """
    if count < 1:
        msg = "At least one value update is required"
        raise ValueError(msg)
    rng = np.random.default_rng(0)
    for _ in range(count):
        updated = a.copy()
        scale = rng.uniform(0.98, 1.02, a.shape[0])
        updated.data *= np.repeat(scale, np.diff(a.indptr))
        if np.array_equal(updated.data, a.data):
            msg = "Value update did not change any matrix entries"
            raise ValueError(msg)
        yield updated


def cudss_updates(a: sparse.csr_matrix, b: np.ndarray, updates: Iterable[sparse.csr_matrix]) -> list[CudssUpdate]:
    """Time blocking host-operand cuDSS phases, rejecting incorrect results.

    Setup includes construction and initial host-to-device copies; update includes
    reset_operands and its host-to-device copies. Analysis, numeric factorization,
    and solve are separate; solve includes the device-to-host result copy. Value
    generation, pattern checks and CPU reference validation are outside those times.
    A changed CSR pattern recreates the solver and analysis before factorization.
    """
    import nvmath.sparse.advanced as sa  # noqa: PLC0415

    if (
        a.shape[0] != a.shape[1]
        or b.shape != (a.shape[0],)
        or not np.isfinite(a.data).all()
        or not np.isfinite(b).all()
    ):
        msg = "Initial matrix and demand must be square, compatible and finite"
        raise ValueError(msg)
    results = []
    previous = a.copy()
    with ExitStack() as resources:
        setup_s, solver = timed(lambda: sa.DirectSolver(a, b), reps=1)
        resources.callback(solver.free)
        analysis_s, _ = timed(solver.plan, reps=1)
        for matrix in updates:
            if matrix.shape != a.shape or not np.isfinite(matrix.data).all():
                msg = "Updated matrix must have the original shape and finite values"
                raise ValueError(msg)
            same = np.array_equal(matrix.indptr, previous.indptr) and np.array_equal(matrix.indices, previous.indices)
            if same and np.array_equal(matrix.data, previous.data):
                msg = "Updated matrix has unchanged values"
                raise ValueError(msg)
            if same:
                update_s, _ = timed(partial(solver.reset_operands, a=matrix), reps=1)
            else:
                resources.close()
                setup_s, solver = timed(partial(sa.DirectSolver, matrix, b), reps=1)
                resources.callback(solver.free)
                analysis_s, _ = timed(solver.plan, reps=1)
                update_s = 0.0
            factorize_s, _ = timed(solver.factorize, reps=1)
            solve_s, x = timed(solver.solve, reps=1)
            x = np.asarray(x)
            if x.shape != b.shape or not np.isfinite(x).all():
                msg = "cuDSS update failed CPU reference: solution shape or values are invalid"
                raise AssertionError(msg)
            reference = spsolve(matrix, b, use_umfpack=False)
            scale = max(float(np.abs(reference).max()), np.finfo(float).tiny)
            relative = float(np.abs(x - reference).max() / scale)
            residual = float(np.abs(matrix @ x - b).max())
            norm = float(abs(matrix).sum(axis=1).max() * np.abs(x).max() + np.abs(b).max())
            backward = residual / norm if norm else residual
            if not relative <= bwbench.DIRECT_RTOL or not backward <= bwbench.DIRECT_RTOL:
                msg = f"cuDSS update failed CPU reference: relative error {relative:.3g}, backward error {backward:.3g}"
                raise AssertionError(msg)
            results.append(
                CudssUpdate(not same, setup_s, analysis_s, update_s, factorize_s, solve_s, relative, backward)
            )
            previous = matrix.copy()
            setup_s = analysis_s = 0.0
    if not results:
        msg = "At least one updated matrix is required"
        raise ValueError(msg)
    return results


def report_updates(a: sparse.csr_matrix, b: np.ndarray) -> None:
    """Print phase timings only after every update passed its correctness checks."""
    warm_cudss()
    print("  cuDSS controlled row-scaled updates (not Monte Carlo draws):", flush=True)
    print(
        "  seconds: setup/initial transfer | analysis | update/transfer | factorize | solve/return transfer",
        flush=True,
    )
    for number, result in enumerate(cudss_updates(a, b, value_updates(a)), 1):
        print(
            f"    update {number}: {result.setup_s:.3g} {result.analysis_s:.3g} {result.update_s:.3g}"
            f" {result.factorize_s:.3g} {result.solve_s:.3g}; replanned {result.replanned}"
            f"; CPU relative error {result.relative_error:.3g}, backward error {result.backward_error:.3g}",
            flush=True,
        )
    print(f"  process peak RSS (includes CPU validation): {bwbench.peak_rss_bytes() / 1e6:.3g} MB", flush=True)


def main() -> None:  # noqa: PLR0915  (one block per solver)
    """Time each solver on the release mounted at /ecoinvent and print the results."""
    import bw2calc.utils as bu  # noqa: PLC0415

    try:
        from PyKLU import Klu  # noqa: PLC0415
    except ImportError:  # conda-forge has no pyklu
        Klu = None  # noqa: N806

    a = build(Path("/ecoinvent"))
    n = a.shape[0]
    rng = np.random.default_rng(0)
    b = np.zeros(n)
    b[rng.choice(n, 30, replace=False)] = 1.0  # a sparse demand, like a few functional units
    print(
        f"ecoinvent in /ecoinvent: n {n}, nnz {a.nnz}; bw2calc {version('bw2calc')}, scipy {version('scipy')}"
        f", scikit-umfpack {version('scikit-umfpack')}, pyklu {version('pyklu') if Klu else 'none'}",
        flush=True,
    )
    # The BLAS libraries mapped once bw2calc has imported its solvers. threadpoolctl misses the
    # reference BLAS that PyPI's scikit-umfpack links, so read the process's own memory map.
    libs = {Path(line.split()[-1]).name for line in Path("/proc/self/maps").read_text().splitlines()}
    blas = sorted(lib for lib in libs if lib.startswith("lib") and ("blas" in lib or "mkl_rt" in lib))
    print(f"  BLAS loaded: {', '.join(blas)}", flush=True)

    if "--cudss-updates" in sys.argv:
        report_updates(a, b)
        return

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

    if Klu is not None:
        csc = a.tocsc()
        csc.sort_indices()
        s, k = timed(lambda: Klu(csc))
        report("KLU pyklu (A, AMD + BTF)", s, k.solve)

    if "--pardiso" in sys.argv:
        bwbench.point_pypardiso_at_mkl()
        import pypardiso  # noqa: PLC0415

        def pardiso() -> pypardiso.PyPardisoSolver:
            p = pypardiso.PyPardisoSolver()
            p.factorize(a)
            return p

        s, p = timed(pardiso)

        def refactorize() -> None:
            # Phase 22: the numeric factorization only, the analysis reused, as cuDSS's refactorize.
            p.set_phase(22)
            p._call_pardiso(a, np.zeros((n, 1)))  # noqa: SLF001  (factorize() always runs phase 12)

        again, _ = timed(refactorize)
        report("PARDISO pypardiso (A)", s, lambda r: p.solve(a, r), f" refactorize {again:.3f} s")

    if "--cudss" in sys.argv:
        with ExitStack() as resources:
            report(f"cuDSS nvmath {version('nvidia-cudss-cu12')} (A)", *time_cudss(a, b, resources=resources))

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
