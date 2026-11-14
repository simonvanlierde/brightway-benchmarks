"""Sparse solvers bw2calc does not pick itself, patched in where it binds its own.

``BWBENCH_SOLVER`` names one for the bw2calc suite (asv's ``klu`` and ``umfpack-T``
environments, ``bwbench compare``'s ``accelerate`` arm); ``scripts/solver_lci.py`` patches them
in by hand. Brightway is imported only by the functions that patch it, so the module itself
loads on a host without Brightway.
"""

import ctypes
import functools
import os
import subprocess
import sys
import weakref
from collections.abc import Callable
from pathlib import Path

import numpy as np
from scipy import sparse

Solve = Callable[[np.ndarray], np.ndarray]


def umfpack_transposed(a: sparse.spmatrix) -> Solve:
    """Factorize A's CSR arrays, which are Aᵀ in CSC: less fill than A on LCA matrices."""
    import scikits.umfpack as um  # noqa: PLC0415

    # A copy: UMFPACK reads the matrix again in each solve, and Monte Carlo and IterativeLCA
    # change the technosphere matrix in place after factorizing it.
    m = sparse.csr_matrix(a, copy=True)
    # 64-bit indices ("dl"), as bw2calc 3.1.0's lu_solver: "di" runs out of memory on large
    # matrices (scipy/scipy#8278).
    m.indices, m.indptr = m.indices.astype(np.int64), m.indptr.astype(np.int64)
    ctx = um.UmfpackContext("dl")
    ctx.numeric(m)
    return lambda b: ctx.solve(um.UMFPACK_A, m, np.asarray(b, dtype=np.float64), autoTranspose=True)


def klu(a: sparse.spmatrix) -> Solve:
    """Factorize A with KLU, which splits it into blocks first (block triangular form)."""
    from PyKLU import Klu  # noqa: PLC0415

    # A copy: sort_indices works in place, and a CSC input may share the caller's arrays.
    m = sparse.csc_matrix(a, copy=True)
    m.sort_indices()
    k = Klu(m)
    return lambda b: k.solve(np.asarray(b, dtype=np.float64))


ACCELERATE_C = Path(__file__).with_name("accelerate.c")


@functools.cache
def accelerate_library() -> ctypes.CDLL:
    """``accelerate.c``, compiled beside itself on first use (and again when it changes) and loaded.

    It needs macOS with the Xcode Command Line Tools and the macOS 15.5 SDK or newer.
    """
    if sys.platform != "darwin":
        msg = "Apple Accelerate is macOS only"
        raise NotImplementedError(msg)  # timecase reports the arm as missing with this reason
    lib = ACCELERATE_C.with_suffix(".dylib")
    if not lib.exists() or lib.stat().st_mtime < ACCELERATE_C.stat().st_mtime:
        tmp = lib.with_suffix(f".{os.getpid()}.tmp")  # then a rename: no other process loads half a file
        cc = ["cc", "-O2", "-shared", "-framework", "Accelerate", str(ACCELERATE_C), "-o", str(tmp)]
        try:
            proc = subprocess.run(cc, capture_output=True, text=True, check=False)  # noqa: S603 - Apple's cc
        except FileNotFoundError:
            proc = subprocess.CompletedProcess(cc, 127, "", "cc not found: install the Xcode Command Line Tools")
        if proc.returncode:
            lines = proc.stderr.strip().splitlines()
            why = next((line for line in lines if "error" in line), lines[-1] if lines else f"exit {proc.returncode}")
            msg = f"cc could not build {ACCELERATE_C.name}: {why}"
            raise RuntimeError(msg)
        tmp.replace(lib)
    c = ctypes.CDLL(str(lib))
    c.bw_factor.restype = ctypes.c_void_p
    c.bw_factor.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
    c.bw_solve.restype = None
    c.bw_solve.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
    c.bw_free.restype = None
    c.bw_free.argtypes = [ctypes.c_void_p]
    return c


def accelerate(a: sparse.spmatrix) -> Solve:
    """Factorize A with Apple Accelerate's sparse LU (threshold partial pivoting), through ``accelerate.c``."""
    lib = accelerate_library()
    m = sparse.csc_matrix(a)
    m.sum_duplicates()  # sorted, unique row indices, as Accelerate expects
    n = m.shape[0]
    colptr, rows = m.indptr.astype(np.int64), m.indices.astype(np.int32)
    vals = np.ascontiguousarray(m.data, dtype=np.float64)
    status = ctypes.c_int(0)
    f = lib.bw_factor(n, colptr.ctypes.data, rows.ctypes.data, vals.ctypes.data, ctypes.byref(status))
    if not f:
        msg = f"Accelerate's sparse LU failed: SparseStatus_t {status.value}"
        raise RuntimeError(msg)

    def solve(b: np.ndarray) -> np.ndarray:
        x = np.array(b, dtype=np.float64)  # a copy: the solve overwrites it
        lib.bw_solve(f, n, x.ctypes.data)
        return x

    weakref.finalize(solve, lib.bw_free, f)
    return solve


FACTORIZERS: dict[str, Callable[[sparse.spmatrix], Solve]] = {
    "umfpack-T": umfpack_transposed,
    "klu": klu,
    "accelerate": accelerate,
}
CALLS = [0]  # factorizations through the patch; 0 after a run means bw2calc bypassed it


def by_column(solve: Solve) -> Solve:
    """``solve`` for a 1-D or a 2-D right-hand side. UMFPACK's and KLU's solves take one column."""

    def solve_any(b: np.ndarray) -> np.ndarray:
        b = np.asarray(b, dtype=np.float64)  # bw2calc passes dense right-hand sides only
        if b.ndim == 1:
            return solve(b)
        return np.column_stack([solve(column) for column in b.T])

    return solve_any


def patch(factorize: Callable[[sparse.spmatrix], Solve]) -> None:
    """Route ``spsolve``, ``factorized`` and ``lu_solver`` in every loaded bw2calc module through ``factorize``.

    Each bw2calc module binds these names at import, and which modules hold them changes
    between releases: ``lca_base`` up to 2.2.2, also ``multi_lca``, ``iterative_lca`` and
    ``fast_supply_arrays`` from 2.3, ``fast_scores`` from 3.0, and ``lu_solver`` from 3.1.0.
    So every copy is replaced; call this after ``import bw2calc``, which loads them all.
    """

    def factorized(a: sparse.spmatrix) -> Solve:
        CALLS[0] += 1
        return by_column(factorize(a))

    def spsolve(a: sparse.spmatrix, b: np.ndarray, *_: object, **__: object) -> np.ndarray:
        return factorized(a)(b)

    def lu_solver(a: sparse.spmatrix, copy: bool = True) -> Solve:  # noqa: ARG001, FBT001, FBT002 - both solvers copy
        return factorized(a)

    replacements = {"spsolve": spsolve, "factorized": factorized, "lu_solver": lu_solver}
    for name, module in list(sys.modules.items()):
        if name == "bw2calc" or name.startswith("bw2calc."):
            for attr, fn in replacements.items():
                if hasattr(module, attr):
                    setattr(module, attr, fn)


def patch_from_env() -> str | None:
    """Patch the solver ``$BWBENCH_SOLVER`` names into bw2calc; the name, or None when unset."""
    name = os.environ.get("BWBENCH_SOLVER")
    if not name:
        return None
    if name not in FACTORIZERS:
        msg = f"BWBENCH_SOLVER={name!r}: one of {', '.join(FACTORIZERS)}"
        raise ValueError(msg)
    import bw2calc  # noqa: F401, PLC0415 - loads the modules patch() replaces names in

    patch(FACTORIZERS[name])
    return name


def assert_reached() -> None:
    """Fail when ``$BWBENCH_SOLVER`` is set but bw2calc has not called the patched solver yet."""
    name = os.environ.get("BWBENCH_SOLVER")
    if name and not CALLS[0]:
        msg = f"bw2calc never called the patched {name}: its solver names have moved"
        raise AssertionError(msg)
