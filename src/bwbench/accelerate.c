/* Apple Accelerate's sparse LU for bwbench.solvers, which compiles this file and loads it with
 * ctypes. Accelerate's C API is Clang overloads with structs passed by value, which ctypes cannot
 * call directly. SparseFactorizationLU needs the macOS 15.5 SDK or newer. */
#include <Accelerate/Accelerate.h>
#include <stdlib.h>

/* The LU factorization of the n x n CSC matrix (sorted row indices), or NULL with *status set. */
void *bw_factor(int n, long *colptr, int *rows, double *vals, int *status) {
    SparseMatrix_Double a = {
        .structure = {.rowCount = n,
                      .columnCount = n,
                      .columnStarts = colptr,
                      .rowIndices = rows,
                      .attributes = {.kind = SparseOrdinary},
                      .blockSize = 1},
        .data = vals,
    };
    SparseOpaqueFactorization_Double *f = malloc(sizeof *f);
    if (f == NULL) {
        *status = SparseInternalError;
        return NULL;
    }
    *f = SparseFactor(SparseFactorizationLU, a);
    *status = f->status;
    if (f->status != SparseStatusOK) {
        SparseCleanup(*f);
        free(f);
        return NULL;
    }
    return f;
}

/* Overwrite x (n values) with the solution of A x = x. */
void bw_solve(void *f, int n, double *x) {
    DenseVector_Double v = {.count = n, .data = x};
    SparseSolve(*(SparseOpaqueFactorization_Double *)f, v);
}

void bw_free(void *f) {
    SparseCleanup(*(SparseOpaqueFactorization_Double *)f);
    free(f);
}
