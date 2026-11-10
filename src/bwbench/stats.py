"""Structural statistics of a technosphere matrix: aggregates only, safe to publish for licensed data.

``measure`` is the calibration oracle (``tests/test_measure.py``) and what
``scripts/measure_stats.py`` and ``scripts/calibration_sweep.py`` record. ``fill_bounds`` needs
pymetis, a development dependency.
"""

from __future__ import annotations

import math
import time
from collections import Counter
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import numpy as np
from scipy import sparse
from scipy.sparse import csgraph
from scipy.sparse import linalg as sla

if TYPE_CHECKING:
    from numpy.typing import NDArray

DENSE_RADIUS_MAX_PRODUCTS = 1000  # largest system solved densely when ARPACK fails (0.36 s at 1000)


def spectral_radius(m: sparse.csc_matrix | sparse.csr_matrix) -> float | None:
    """Largest ``|eigenvalue|`` of ``m``; None if ARPACK did not converge and ``m`` is too big for a dense solve."""
    n = m.shape[0]
    if m.nnz == 0:
        return 0.0
    if n >= 3:  # eigs needs k < n - 1
        try:
            eig = sla.eigs(m, k=1, which="LM", return_eigenvectors=False, tol=1e-8, maxiter=n * 10, v0=np.ones(n))
            return float(np.abs(eig).max())
        except sla.ArpackNoConvergence:
            # A system with no loops is nilpotent: every eigenvalue is 0 and ARPACK cannot find one.
            if n > DENSE_RADIUS_MAX_PRODUCTS:
                return None
    return float(np.abs(np.linalg.eigvals(m.toarray())).max())


# Bands of entries per supplier row for overlap_by_band, both ends included. A row's entries
# are its consumers plus its own production, so "17-64" means 16 to 63 consumers.
OVERLAP_BANDS = (
    (2, 4),
    (5, 16),
    (17, 64),
    (65, 256),
    (257, 1 << 62),
)

QUANTILES = (0.0, 0.1, 0.25, 0.5, 0.75, 0.9, 0.99, 1.0)


def _quantiles(values: NDArray, *, extremes: bool = True) -> dict[str, float]:
    """The ``QUANTILES`` of ``values``, and their mean: a distribution, never the values themselves.

    ``extremes=False`` leaves out the minimum, the maximum and the mean. The first two are each
    one value, and a heavy tail makes the mean one too: for amounts from a licensed database,
    each would publish a single dataset's figure.
    """
    v = np.asarray(values, dtype=np.float64)
    if v.size == 0:
        return {}
    qs = QUANTILES if extremes else [q for q in QUANTILES if 0 < q < 1]
    return ({"mean": float(v.mean())} if extremes else {}) | {
        f"q{round(q * 100):02d}": float(np.quantile(v, q)) for q in qs
    }


@dataclass(frozen=True)
class Stats:
    """Structural statistics of a technosphere: aggregates only, safe to publish for licensed data.

    ``X = I - A`` after scaling each column to a production amount of 1, so ``X[i, j]`` is how
    much of product ``i`` one unit of product ``j`` takes in. Degrees count nonzero entries.
    """

    products: int
    entries: int  # nonzero inputs (off-diagonal)
    inputs_per_product: dict[str, float]  # nonzero entries per column
    consumers_per_supplier: dict[str, float]  # nonzero entries per row
    log10_abs_input: dict[str, float]  # distribution of log10 |X[i, j]|, quantiles only
    negative_input_share: float  # inputs with X < 0: wastes sent to treatment, and a treatment's own inputs
    column_abs_sum: dict[str, float]  # sum over i of |X[i, j]|, quantiles only
    loops: dict[str, float]  # strongly connected components of more than one product
    spectral_radius: float | None  # largest |eigenvalue| of X; None if ARPACK failed on a large X
    spectral_radius_abs: float | None  # largest eigenvalue of |X|, an upper bound on the above
    lu_fill: dict[str, float]  # nnz(L + U) / nnz(A) per SuperLU column ordering, of A and of A^T
    factor_seconds: dict[str, float]  # median of the SuperLU factorizations, per ordering, of A and of A^T
    same_location_share: float | None = None  # inputs whose supplier has the consumer's location
    same_sector_share: float | None = None  # the same for the sector; "" (unknown) is left out
    # What drives LU fill beyond degrees and loops (see dense_rows and the fields below).
    dense_rows: dict[str, int] | None = None  # supplier rows above and just below COLAMD's dense cut-off
    ata_fill: float | None = None  # nnz(A^T A) / nnz(A): the pattern COLAMD orders
    overlap_by_band: dict[str, dict[str, float]] | None = None  # per supplier size band, see OVERLAP_BANDS
    copied_inputs: float | None = None  # share of products with inputs whose list another product has too
    hub_jaccard: float | None = None  # mean Jaccard overlap of the 50 largest suppliers' consumer sets
    overlap_without_hubs: float | None = None  # ata_fill / row_pairs with the top 1% of supplier rows removed
    row_pairs: float | None = None  # sum over rows of (entries per row)^2 / nnz(A): ata_fill if no two rows overlapped
    clustering: float | None = None  # transitivity of A + A^T without its diagonal
    reciprocity: float | None = None  # inputs (i, j) for which (j, i) is an input too
    core_after_hubs: float | None = None  # share of products in the 2-core of A + A^T without the top 1% by degree
    lu_fill_no_pivoting: dict[str, float] | None = None  # lu_fill with diag_pivot_thresh=0
    off_diagonal_pivots: dict[str, float] | None = None  # share of columns pivoted off the diagonal, default threshold
    fill_bounds: dict[str, dict[str, float]] | None = None  # see fill_bounds(); COLAMD keys need the factorizations


def measure(
    technosphere: sparse.spmatrix,
    locations: list[str] | None = None,
    sectors: list[str] | None = None,
    *,
    repeats: int = 3,
) -> Stats:
    """Structural statistics of a technosphere matrix ``A`` (production on the diagonal).

    ``repeats`` SuperLU factorizations per ordering give the median time, for A and for A^T
    (keys ending in ``(A^T)``); 0 skips them, and the fill with them. ``fill_bounds`` needs
    pymetis; its COLAMD keys use SuperLU's column orderings, so 0 leaves them out too.
    """
    a = sparse.csc_matrix(technosphere, dtype=np.float64)
    n = a.shape[0]
    if n == 0 or not np.all(a.diagonal()):
        msg = "every product needs a nonzero net production on the diagonal"  # names no dataset
        raise ValueError(msg)
    a = a @ sparse.diags(1.0 / a.diagonal())  # production amount 1 in every column
    x = (sparse.identity(n, format="csc") - a).tocsc()
    x.setdiag(0.0)
    x.eliminate_zeros()
    xa = abs(x)

    _, labels = csgraph.connected_components(x, directed=True, connection="strong")
    sizes = np.bincount(labels)
    loops = sizes[sizes > 1]

    fill, seconds, fill_no_pivoting, pivots, perms = {}, {}, {}, {}, {}
    # A^T too: bw2calc's decompose_technosphere factorizes A, scipy's spsolve on CSR input A^T.
    for m, suffix in ((a, ""), (a.T.tocsc(), " (A^T)")) if repeats else ():
        for order in ("COLAMD", "MMD_AT_PLUS_A"):
            times = []
            for _ in range(repeats):
                t0 = time.perf_counter()
                lu = sla.splu(m, permc_spec=order)
                times.append(time.perf_counter() - t0)
            fill[order + suffix] = _lu_fill(lu, m)
            if order == "COLAMD":
                perms[order + suffix] = lu.perm_c
            seconds[order + suffix] = float(np.median(times))
            if not suffix:
                # Column i lands at perm_c[i] and row i at perm_r[i]: the pivot is A[i, i] when they agree.
                pivots[order] = float(np.mean(lu.perm_r != lu.perm_c))
                fill_no_pivoting[order] = _lu_fill(sla.splu(a, permc_spec=order, diag_pivot_thresh=0.0), a)

    rows, cols = x.nonzero()

    def same_share(labels_: list[str] | None) -> float | None:
        if labels_ is None:
            return None
        lab = np.asarray(labels_)
        known = (lab[rows] != "") & (lab[cols] != "")
        return float(np.mean(lab[rows][known] == lab[cols][known])) if known.any() else None

    return Stats(
        products=n,
        entries=int(x.nnz),
        # The largest count describes one dataset, so degrees leave out their extremes too.
        inputs_per_product=_quantiles(np.diff(x.indptr), extremes=False),
        consumers_per_supplier=_quantiles(np.bincount(rows, minlength=n), extremes=False),
        log10_abs_input=_quantiles(np.log10(xa.data), extremes=False),
        negative_input_share=float(np.mean(x.data < 0)) if x.nnz else 0.0,
        column_abs_sum=_quantiles(np.ravel(xa.sum(axis=0)), extremes=False),
        loops={
            "components": int(loops.size),
            "largest": int(loops.max()) if loops.size else 0,
            "products_in_loops": int(loops.sum()),
        },
        spectral_radius=spectral_radius(x),
        spectral_radius_abs=spectral_radius(xa),
        lu_fill=fill,
        factor_seconds=seconds,
        same_location_share=same_share(locations),
        same_sector_share=same_share(sectors),
        **_fill_drivers(a, x, locations, sectors),
        lu_fill_no_pivoting=fill_no_pivoting or None,
        off_diagonal_pivots=pivots or None,
        fill_bounds=fill_bounds(a, perms),
    )


def _shared_pairs(
    joined: sparse.coo_matrix, locations: list[str] | None, sectors: list[str] | None
) -> dict[str, float]:
    """For consumer pairs that share a supplier: how many they share, and how alike they are.

    ``joined`` is Q^T Q for one band of supplier rows Q. Same-sector pairs in different
    locations point at regional copies of one technology; same-location pairs at regional
    markets. Aggregates only.
    """
    upper = joined.row < joined.col
    i, j = joined.row[upper], joined.col[upper]
    out = {"suppliers_shared": float(joined.data[upper].mean()) if i.size else 0.0}
    for key, labels in (("same_location", locations), ("same_sector", sectors)):
        if labels is not None and i.size:
            lab = np.asarray(labels)
            known = (lab[i] != "") & (lab[j] != "")
            out[key] = float(np.mean(lab[i][known] == lab[j][known])) if known.any() else 0.0
    return out


def _lu_fill(lu: Any, a: sparse.csc_matrix) -> float:  # noqa: ANN401 - scipy's SuperLU object
    """nnz(L + U) / nnz(A), counting the shared unit diagonal once."""
    return float((lu.L.nnz + lu.U.nnz - a.shape[0]) / a.nnz)


def _etree(a: sparse.csc_matrix, *, ata: bool) -> NDArray[np.int64]:
    """Elimination tree of the Cholesky factor of A (upper part used), or of A^T A when ``ata``.

    CSparse's cs_etree (Davis, Direct Methods for Sparse Linear Systems, 2006, section 4.1).
    """
    m, n = a.shape
    parent = np.full(n, -1, dtype=np.int64)
    ancestor = [-1] * n
    prev = [-1] * m
    ap, ai = a.indptr.tolist(), a.indices.tolist()
    par = parent.tolist()
    for k in range(n):
        for p in range(ap[k], ap[k + 1]):
            r = ai[p]
            i = prev[r] if ata else r
            while i != -1 and i < k:
                inext = ancestor[i]
                ancestor[i] = k
                if inext == -1:
                    par[i] = k
                i = inext
            if ata:
                prev[r] = k
    parent[:] = par
    return parent


def _postorder(parent: NDArray[np.int64]) -> list[int]:
    """A postorder of the forest ``parent``: children before parents, each subtree contiguous."""
    n = parent.size
    children: list[list[int]] = [[] for _ in range(n)]
    roots = []
    for j in range(n - 1, -1, -1):  # reversed, so children pop off the stack in id order
        (children[parent[j]] if parent[j] != -1 else roots).append(j)
    post, stack = [], list(roots)
    expanded = [False] * n
    while stack:
        j = stack[-1]
        if expanded[j]:
            post.append(stack.pop())
        else:
            expanded[j] = True
            stack.extend(children[j])
    return post


def cholesky_counts(  # noqa: C901, PLR0912, PLR0915 - cs_counts, ported in one piece to compare against it
    a: sparse.spmatrix, *, ata: bool
) -> tuple[NDArray[np.int64], NDArray[np.int64]]:
    """Column counts of the Cholesky factor L of A (symmetric pattern) or of A^T A, and its etree.

    Symbolic only, in about O(nnz(A)) steps, without forming A^T A: CSparse's cs_counts
    (Gilbert, Ng and Peyton's skeleton-matrix method). Counts include the diagonal, so
    ``counts.sum()`` is nnz(L). Values are ignored; only the pattern matters.
    """
    a = sparse.csc_matrix(a, copy=True)  # sort_indices works in place
    a.sort_indices()
    m, n = a.shape
    parent = _etree(a, ata=ata)
    post = _postorder(parent)
    par = parent.tolist()
    at = a.T.tocsc()  # column J of A^T is row J of A
    at.sort_indices()
    atp, ati = at.indptr.tolist(), at.indices.tolist()
    first = [-1] * n
    delta = [0] * n
    for k in range(n):
        j = post[k]
        delta[j] = 1 if first[j] == -1 else 0  # 1 if j is a leaf
        while j != -1 and first[j] == -1:
            first[j] = k
            j = par[j]
    head, nxt = [-1] * (n + 1), [-1] * m
    if ata:
        # Row i of A is a clique in A^T A: visit it once, at its earliest column in postorder.
        where = [0] * n
        for k, j in enumerate(post):
            where[j] = k
        for i in range(m):
            k = min((where[c] for c in ati[atp[i] : atp[i + 1]]), default=n)
            nxt[i] = head[k]
            head[k] = i
    ancestor = list(range(n))
    maxfirst = [-1] * n
    prevleaf = [-1] * n
    for k in range(n):
        j = post[k]
        if par[j] != -1:
            delta[par[j]] -= 1  # j is not a root
        rows = []
        if ata:
            r = head[k]
            while r != -1:
                rows.append(r)
                r = nxt[r]
        else:
            rows.append(j)
        for r in rows:
            for p in range(atp[r], atp[r + 1]):
                i = ati[p]
                # cs_leaf: is j a leaf of row i's subtree, and where does it meet the previous leaf?
                if i <= j or first[j] <= maxfirst[i]:
                    continue
                maxfirst[i] = first[j]
                jprev = prevleaf[i]
                prevleaf[i] = j
                delta[j] += 1  # A(i, j) is in the skeleton matrix
                if jprev != -1:
                    q = jprev
                    while q != ancestor[q]:
                        q = ancestor[q]
                    s = jprev
                    while s != q:  # path compression
                        sparent = ancestor[s]
                        ancestor[s] = q
                        s = sparent
                    delta[q] -= 1  # the overlap at the least common ancestor
        if par[j] != -1:
            ancestor[j] = par[j]
    for j in post:  # children come first, so each subtree's sum is complete when its root adds it
        if par[j] != -1:
            delta[par[j]] += delta[j]
    return np.asarray(delta, dtype=np.int64), parent


def tree_height(parent: NDArray[np.int64]) -> int:
    """Edges on the longest leaf-to-root path of the forest ``parent``."""
    depth = np.zeros(parent.size, dtype=np.int64)
    for j in reversed(_postorder(parent)):  # parents before children
        if parent[j] != -1:
            depth[j] = depth[parent[j]] + 1
    return int(depth.max()) if depth.size else 0


def _bisection_separator(graph: sparse.csr_matrix) -> int:
    """Size of a vertex separator from METIS's edge bisection of ``graph``.

    The smallest vertex set that covers every cut edge: by Konig's theorem its size is a
    maximum matching of the bipartite graph of cut edges.
    """
    import pymetis  # noqa: PLC0415 - only fill_bounds needs it

    n = graph.shape[0]
    if n < 2 or graph.nnz == 0:  # nothing to separate
        return 0
    _, parts = pymetis.part_graph(2, pymetis.CSRAdjacency(graph.indptr, graph.indices), options=pymetis.Options(seed=0))
    parts = np.asarray(parts)
    cut = graph[parts == 0][:, parts == 1].tocsr()
    return int((csgraph.maximum_bipartite_matching(cut, perm_type="column") != -1).sum())


def fill_bounds(a: sparse.csc_matrix, perms: dict[str, NDArray]) -> dict[str, dict[str, float]]:
    """Fill-governing structure of ``a``, under METIS and under SuperLU's COLAMD orderings.

    - ``COLAMD`` and ``COLAMD (A^T)``, one per entry of ``perms`` (SuperLU's ``perm_c``):
      with partial pivoting, L + U of A Q fits in the Cholesky pattern of (A Q)^T (A Q)
      (George and Ng 1987). ``bound`` is 2 nnz(L_c) - n over nnz(A), on the scale of
      ``lu_fill``. For the ``(A^T)`` key that pattern is A A^T.
    - ``METIS``: the same for A + A^T under METIS's nested dissection, the fill LU gets
      in that order without off-diagonal pivots. It needs only A.
    - ``height`` is the elimination tree's longest path and ``front`` the largest column
      count of L_c, both as a share of n: long trees and big fronts mean large dense blocks.
    - ``separator``: ``top`` is the vertex separator of A + A^T from METIS's bisection, as a
      share of n. Nested dissection's fill grows with it.
    """
    import pymetis  # noqa: PLC0415 - not a runtime dependency of the benchmarks

    n = a.shape[0]
    pattern = (a != 0).astype(np.float64).tocsc()
    sym = ((pattern + pattern.T) != 0).astype(np.float64).tocsr()

    def summary(counts: NDArray[np.int64], parent: NDArray[np.int64]) -> dict[str, float]:
        return {
            "bound": float((2 * counts.sum() - n) / a.nnz),
            "height": tree_height(parent) / n,
            "front": float(counts.max()) / n,
        }

    out = {}
    for key, perm in perms.items():
        order = np.argsort(perm)  # column i of A lands at perm[i]
        m = (pattern.T if key.endswith("(A^T)") else pattern).tocsc()[:, order]
        out[key] = summary(*cholesky_counts(m, ata=True))
    graph = sym.copy()
    graph.setdiag(0)
    graph.eliminate_zeros()
    graph = graph.astype(np.int32).tocsr()
    dissection = np.asarray(pymetis.nested_dissection(pymetis.CSRAdjacency(graph.indptr, graph.indices))[0])
    # nested_dissection returns (perm, iperm); perm[k] is the vertex eliminated k-th.
    out["METIS"] = summary(*cholesky_counts(sym[dissection][:, dissection], ata=False))
    out["separator"] = {"top": _bisection_separator(graph) / n}
    return out


def _fill_drivers(
    a: sparse.csc_matrix, x: sparse.csc_matrix, locations: list[str] | None, sectors: list[str] | None
) -> dict[str, Any]:
    """Structural statistics that bear on LU fill: aggregates only, like the rest of ``Stats``."""
    n = a.shape[0]
    pattern = (a != 0).astype(np.float64).tocsr()
    row_counts = np.diff(pattern.indptr)
    cutoff = max(16, int(10 * math.sqrt(n)))  # COLAMD's default dense-row cut-off, as SuperLU calls it
    ata = (pattern.T @ pattern).nnz

    p = (x != 0).astype(np.float64)
    sym = ((p + p.T) != 0).astype(np.float64).tocsr()
    degree = np.diff(sym.indptr)
    top_rows = np.argsort(-row_counts, kind="stable")  # ties in id order, so the same 50 every run
    big = pattern[top_rows[:50]]
    shared = (big @ big.T).toarray()
    union = row_counts[top_rows[:50], None] + row_counts[None, top_rows[:50]] - shared
    upper = np.triu_indices(shared.shape[0], k=1)
    rest = pattern[np.sort(top_rows[math.ceil(0.01 * n) :])]
    rest_pairs = float((np.diff(rest.indptr).astype(np.float64) ** 2).sum())

    # Which suppliers' consumers overlap: per band of consumer counts, nnz(Q^T Q) over the
    # summed squared row counts (1: no shared pairs), and the band's share of all row pairs.
    squares = row_counts.astype(np.float64) ** 2
    by_band = {}
    for low, high in OVERLAP_BANDS:
        rows_in = np.flatnonzero((row_counts >= low) & (row_counts <= high))
        pairs = float(squares[rows_in].sum())
        if pairs:
            band = pattern[rows_in]
            joined = (band.T @ band).tocoo()
            by_band[f"{low}+" if high == OVERLAP_BANDS[-1][1] else f"{low}-{high}"] = {
                "overlap": float(joined.nnz / pairs),
                "pairs_share": pairs / float(squares.sum()),
                **_shared_pairs(joined, locations, sectors),
            }

    # Products whose input list (off the diagonal) another product has exactly too.
    lists = [x.indices[x.indptr[j] : x.indptr[j + 1]].tobytes() for j in range(n) if x.indptr[j + 1] > x.indptr[j]]
    counts = Counter(lists)
    copied = sum(c for c in counts.values() if c > 1) / len(lists) if lists else 0.0

    triangles = 0.0
    for start in range(0, n, 2_000):  # in blocks, so S @ S never sits in memory whole
        block = sym[start : start + 2_000]
        triangles += float((block @ sym).multiply(block).sum())
    triples = float((degree * (degree - 1)).sum())

    alive = np.ones(n, dtype=bool)
    alive[np.argsort(-degree, kind="stable")[: math.ceil(0.01 * n)]] = False  # ties in id order
    deg = sym @ alive.astype(np.float64)
    while (low := alive & (deg < 2)).any():  # peel to the 2-core: no node with fewer than 2 neighbours
        alive[low] = False
        deg -= sym @ low.astype(np.float64)

    return {
        "dense_rows": {
            "cutoff": cutoff,
            "above": int((row_counts > cutoff).sum()),
            "half_to_cutoff": int(((row_counts > cutoff // 2) & (row_counts <= cutoff)).sum()),
        },
        "ata_fill": float(ata / a.nnz),
        "row_pairs": float((row_counts.astype(np.float64) ** 2).sum() / a.nnz),
        "overlap_by_band": by_band,
        "copied_inputs": float(copied),
        "hub_jaccard": float(np.mean(shared[upper] / np.maximum(union[upper], 1))) if upper[0].size else 0.0,
        "overlap_without_hubs": float((rest.T @ rest).nnz / rest_pairs) if rest_pairs else 0.0,
        "clustering": triangles / triples if triples else 0.0,
        "reciprocity": float(p.multiply(p.T).nnz / p.nnz) if p.nnz else 0.0,
        "core_after_hubs": float(alive.mean()),
    }
