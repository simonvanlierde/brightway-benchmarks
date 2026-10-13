"""Seeded synthetic LCA systems, written as bw_processing datapackages.

The technosphere is ``A = I - X``: one production exchange of 1 per product on the
diagonal, and ``inputs`` random upstream inputs per column whose amounts sum to less
than 0.5. So ``A`` is column diagonally dominant: always invertible, and every
iterative solver converges on it. The same seed gives the same system on every machine.

Only numpy and scipy are needed to build the arrays. ``write_datapackages`` also needs
bw_processing and runs in the benchmark container.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
from dataclasses import asdict, dataclass
from importlib.metadata import version
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
from scipy import sparse
from scipy.sparse import csgraph
from scipy.sparse import linalg as sla

if TYPE_CHECKING:
    from numpy.typing import NDArray

# Bump when generate() or the stored reference changes. It is part of the cache key, and
# benchmarks on generated data use it as their asv `version`, so old results are dropped.
# That replaces asv's hash of the benchmark code: bump it when their timed code changes too.
GENERATOR_VERSION = "2"
INPUTS_SHARE = 0.5  # upper bound on the sum of input amounts per column
NEUMANN_TOL = 1e-17  # column norm of the last series term at which the reference stops
REFERENCE_PRODUCTS = 30  # reference scores are stored for products 0 to 29, the most MultiScores demands


@dataclass(frozen=True)
class Size:
    """Shape of one synthetic system."""

    products: int
    inputs: int  # upstream inputs per product, before duplicates are dropped
    flows: int  # biosphere flows
    flows_per_product: int = 3
    methods: int = 3


# NOTE: only `products` is sourced. `inputs` and `flows` are guesses until the generator
# is calibrated against public summary statistics of each database.
SIZES: dict[str, Size] = {
    "smoke": Size(products=200, inputs=4, flows=30),
    # ecoinvent cut-off: about 20k to 25k products. 20k x 8 inputs gives about 180k
    # technosphere entries, the size bw_synth.py was built for.
    "ecoinvent": Size(products=20_000, inputs=8, flows=4_000),
    # EXIOBASE 3 product by product: 9,800 sectors (49 regions x 200 products), much denser.
    "exiobase": Size(products=9_800, inputs=400, flows=1_100),
    # #131's large Monte Carlo case is 100k products (at 2% fill there, far denser than this).
    "mc100k": Size(products=100_000, inputs=8, flows=4_000),
    # The regionalised system from Brightcon 2026 contribution 59: 250k x 250k.
    "regional": Size(products=250_000, inputs=8, flows=4_000),
}


@dataclass(frozen=True)
class System:
    """One synthetic system as coordinate arrays, with bw2calc's sign convention.

    Technosphere inputs are stored as positive amounts with ``flip`` set, as bw2data
    writes them, so the matrix bw2calc builds is ``A = I - X``.
    """

    size: Size
    seed: int
    tech_rows: NDArray[np.int64]
    tech_cols: NDArray[np.int64]
    tech_data: NDArray[np.float64]
    tech_flip: NDArray[np.bool_]
    bio_rows: NDArray[np.int64]
    bio_cols: NDArray[np.int64]
    bio_data: NDArray[np.float64]
    cf_flows: list[NDArray[np.int64]]  # per method: flow ids
    cf_data: list[NDArray[np.float64]]  # per method: factors

    @property
    def flow_offset(self) -> int:
        """Biosphere flow ids start here, so they never collide with product ids."""
        return self.size.products

    def technosphere(self) -> sparse.csc_matrix:
        """The technosphere matrix bw2calc builds from this system."""
        n = self.size.products
        signed = np.where(self.tech_flip, -self.tech_data, self.tech_data)
        return sparse.csc_matrix((signed, (self.tech_rows, self.tech_cols)), shape=(n, n))

    def biosphere(self) -> sparse.csc_matrix:
        """Biosphere matrix with flows renumbered from 0."""
        shape = (self.size.flows, self.size.products)
        return sparse.csc_matrix((self.bio_data, (self.bio_rows - self.flow_offset, self.bio_cols)), shape=shape)

    def reference_scores(self, products: int = REFERENCE_PRODUCTS) -> list[list[float]]:
        """Score of one unit of each of the first ``products`` products, per method.

        ``reference_scores()[p][m]`` is product ``p`` under method ``m``. This is the
        reference every Brightway result is checked against.
        """
        n = self.size.products
        inputs = sparse.identity(n, format="csr") - self.technosphere().tocsr()
        supply = neumann(inputs, np.eye(n, min(products, n)))
        inventory = self.biosphere() @ supply
        return [
            [float(inventory[f - self.flow_offset, p] @ c) for f, c in zip(self.cf_flows, self.cf_data, strict=True)]
            for p in range(supply.shape[1])
        ]


def neumann(inputs: sparse.csr_matrix, demand: NDArray[np.float64]) -> NDArray[np.float64]:
    """Solve ``(I - inputs) x = demand`` as the series ``demand + inputs @ demand + ...``.

    Shares no code with any solver under test and needs no factorization, so it stays
    cheap at every size. It converges when every column of ``abs(inputs)`` sums to less
    than 1; at ``INPUTS_SHARE`` (0.5) about 57 terms bring the next one below 1e-17.
    """
    x = demand.copy()
    term = demand
    for _ in range(500):
        term = inputs @ term
        x += term
        # With column sums at most 0.5, the rest of the series is no larger than this term.
        if np.abs(term).sum(axis=0).max() < NEUMANN_TOL:
            return x
    msg = "Neumann series did not converge: an input column sums to 1 or more"
    raise ArithmeticError(msg)


def generate(size: Size, seed: int = 0) -> System:
    """Build a synthetic system. Same ``size`` and ``seed``, same arrays."""
    rng = np.random.default_rng(seed)
    n, k = size.products, size.inputs

    # TODO: inputs on uniformly random rows fill SuperLU's L+U to about 60% of a dense  # noqa: FIX002
    # matrix, so timings at "ecoinvent" size and up measure that fill, not a real
    # database. Giving the graph structure is the author's call: review 2026-10-13, row 1.

    cols = np.repeat(np.arange(n, dtype=np.int64), k)
    rows = rng.integers(0, n, size=n * k, dtype=np.int64)
    keep = rows != cols  # no self-loops: the diagonal holds production only
    _, first = np.unique(rows[keep] * n + cols[keep], return_index=True)  # drop repeated cells
    rows, cols = rows[keep][first], cols[keep][first]
    amounts = rng.uniform(0.0, INPUTS_SHARE / k, size=rows.size)

    diag = np.arange(n, dtype=np.int64)
    tech_rows = np.concatenate([diag, rows])
    tech_cols = np.concatenate([diag, cols])
    tech_data = np.concatenate([np.ones(n), amounts])
    tech_flip = np.concatenate([np.zeros(n, dtype=bool), np.ones(rows.size, dtype=bool)])

    m = size.flows_per_product
    bio_cols = np.repeat(np.arange(n, dtype=np.int64), m)
    bio_flows = rng.integers(0, size.flows, size=n * m, dtype=np.int64)
    _, first = np.unique(bio_flows * n + bio_cols, return_index=True)
    bio_rows = bio_flows[first] + n
    bio_cols = bio_cols[first]
    bio_data = rng.lognormal(0.0, 1.0, size=bio_rows.size)

    cf_flows, cf_data = [], []
    for _ in range(size.methods):
        flows = np.sort(rng.choice(size.flows, size=max(1, size.flows // 10), replace=False)).astype(np.int64)
        cf_flows.append(flows + n)
        cf_data.append(rng.lognormal(0.0, 1.0, size=flows.size))

    return System(
        size, seed, tech_rows, tech_cols, tech_data, tech_flip, bio_rows, bio_cols, bio_data, cf_flows, cf_data
    )


def many_groups(n: int) -> object:
    """An in-memory bw_processing datapackage with ``n`` one-entry resource groups on the diagonal."""
    import bw_processing as bwp  # noqa: PLC0415 - only the container has it

    dp = bwp.create_datapackage()
    for i in range(n):
        idx = np.array([(i, i)], dtype=bwp.INDICES_DTYPE)
        dp.add_persistent_vector(matrix="technosphere_matrix", name=f"g{i}", indices_array=idx, data_array=np.ones(1))
    return dp


def method_name(i: int) -> tuple[str, str]:
    """Method identifier as bw2calc's MultiLCA matches it."""
    return ("synthetic", f"method {i}")


def write_datapackages(system: System, folder: Path, *, uncertain: bool = False) -> Path:
    """Write ``system`` as bw_processing datapackages under ``folder``.

    ``inventory/`` holds the technosphere and biosphere, and ``method-<i>/`` one
    characterization each, with the ``identifier`` MultiLCA filters on. They are separate
    because a plain ``LCA`` sums every characterization it is given. With ``uncertain``,
    technosphere inputs get a normal distribution with a 10% standard deviation, for
    Monte Carlo. ``reference.json`` holds ``reference_scores()``.
    """
    import bw_processing as bwp  # noqa: PLC0415 - only the container has it

    def new(name: str):  # noqa: ANN202
        (folder / name).mkdir(parents=True, exist_ok=True)
        fs = bwp.generic_directory_filesystem(dirpath=folder / name)
        return bwp.create_datapackage(fs=fs, name=name, id_=name)

    def indices(rows: NDArray[np.int64], cols: NDArray[np.int64]) -> np.ndarray:
        arr = np.empty(rows.size, dtype=bwp.INDICES_DTYPE)
        arr["row"], arr["col"] = rows, cols
        return arr

    distributions = None
    if uncertain:
        distributions = np.zeros(system.tech_data.size, dtype=bwp.UNCERTAINTY_DTYPE)
        for field in ("shape", "minimum", "maximum"):
            distributions[field] = np.nan
        distributions["loc"] = system.tech_data
        distributions["uncertainty_type"] = np.where(system.tech_flip, 3, 0)  # 3: normal
        distributions["scale"] = np.where(system.tech_flip, 0.1 * system.tech_data, np.nan)

    dp = new("inventory")
    dp.add_persistent_vector(
        matrix="technosphere_matrix",
        name="technosphere",
        indices_array=indices(system.tech_rows, system.tech_cols),
        data_array=system.tech_data,
        flip_array=system.tech_flip,
        distributions_array=distributions,
    )
    dp.add_persistent_vector(
        matrix="biosphere_matrix",
        name="biosphere",
        indices_array=indices(system.bio_rows, system.bio_cols),
        data_array=system.bio_data,
    )
    dp.finalize_serialization()
    for i, (flows, factors) in enumerate(zip(system.cf_flows, system.cf_data, strict=True)):
        dp = new(f"method-{i}")
        dp.add_persistent_vector(
            matrix="characterization_matrix",
            name=f"characterization-{i}",
            identifier=list(method_name(i)),
            indices_array=indices(flows, np.zeros_like(flows)),
            data_array=factors,
            global_index=0,
        )
        dp.finalize_serialization()

    meta = {"size": asdict(system.size), "seed": system.seed, "reference_scores": system.reference_scores()}
    (folder / "reference.json").write_text(json.dumps(meta, indent=2))
    return folder


def data_root() -> Path:
    """Where generated datapackages are cached: ``~/.cache/bwbench`` (under ``.asv/`` in the box)."""
    return Path.home() / ".cache" / "bwbench"


def cache_folder(name: str, *, seed: int, uncertain: bool, bwp_version: str) -> Path:
    """Cache folder for one system: a new one whenever anything that shapes the files changes."""
    key = [asdict(SIZES[name]), seed, uncertain, GENERATOR_VERSION, bwp_version]
    digest = hashlib.sha256(json.dumps(key, sort_keys=True).encode()).hexdigest()[:12]
    return data_root() / f"{name}-{digest}"


def cached(name: str, *, seed: int = 0, uncertain: bool = False) -> Path:
    """Folder of the datapackages for ``SIZES[name]``, generated on first use.

    Written to a temporary folder and renamed, so a run that dies half-way, or two runs at
    once, never leave a folder that looks complete.
    """
    folder = cache_folder(name, seed=seed, uncertain=uncertain, bwp_version=version("bw_processing"))
    if folder.exists():
        return folder
    tmp = folder.with_name(f"{folder.name}.tmp-{os.getpid()}")
    shutil.rmtree(tmp, ignore_errors=True)
    write_datapackages(generate(SIZES[name], seed), tmp, uncertain=uncertain)
    try:
        tmp.rename(folder)
    except OSError:
        if not folder.exists():
            raise
        shutil.rmtree(tmp)  # another run finished first
    return folder


def load(folder: Path) -> tuple[object, list[object], list[float]]:
    """The inventory datapackage, the method datapackages and the reference scores."""
    import bw_processing as bwp  # noqa: PLC0415

    def read(name: str) -> object:
        return bwp.load_datapackage(bwp.generic_directory_filesystem(dirpath=folder / name))

    meta = json.loads((folder / "reference.json").read_text())
    methods = [read(f"method-{i}") for i in range(meta["size"]["methods"])]
    return read("inventory"), methods, meta["reference_scores"]


def as_bw2data(system: System, db: str = "synth", bio: str = "bio") -> tuple[dict, dict, list[list]]:
    """The same system as the dicts ``bw2data.Database.write`` and ``Method.write`` take.

    Returns the biosphere database, the technosphere database, and one CF list per
    method. Product ``i`` has code ``p<i>``; flow ``j`` has code ``f<j>``.
    """
    off = system.flow_offset
    biosphere = {
        (bio, f"f{j}"): {"name": f"flow {j}", "unit": "kilogram", "type": "emission", "categories": ("air",)}
        for j in range(system.size.flows)
    }
    exchanges: list[list[dict]] = [[] for _ in range(system.size.products)]
    for r, c, a, f in zip(system.tech_rows, system.tech_cols, system.tech_data, system.tech_flip, strict=True):
        kind = "technosphere" if f else "production"
        exchanges[c].append({"input": (db, f"p{r}"), "amount": float(a), "type": kind, "unit": "kilogram"})
    for r, c, a in zip(system.bio_rows, system.bio_cols, system.bio_data, strict=True):
        exchanges[c].append(
            {"input": (bio, f"f{r - off}"), "amount": float(a), "type": "biosphere", "unit": "kilogram"}
        )
    technosphere = {
        (db, f"p{i}"): {
            "name": f"process {i}",
            "reference product": f"product {i}",
            "location": "GLO",
            "unit": "kilogram",
            "production amount": 1.0,
            "exchanges": exc,
        }
        for i, exc in enumerate(exchanges)
    }
    cfs = [
        [[(bio, f"f{f - off}"), float(v)] for f, v in zip(flows, factors, strict=True)]
        for flows, factors in zip(system.cf_flows, system.cf_data, strict=True)
    ]
    return biosphere, technosphere, cfs


QUANTILES = (0.0, 0.1, 0.25, 0.5, 0.75, 0.9, 0.99, 1.0)


def _quantiles(values: NDArray, *, extremes: bool = True) -> dict[str, float]:
    """Mean and the ``QUANTILES`` of ``values``: a distribution, never the values themselves.

    ``extremes=False`` leaves out the minimum and maximum, which are each one value: for amounts
    from a licensed database that would publish a single exchange.
    """
    v = np.asarray(values, dtype=np.float64)
    if v.size == 0:
        return {}
    qs = QUANTILES if extremes else [q for q in QUANTILES if 0 < q < 1]
    return {"mean": float(v.mean()), **{f"q{round(q * 100):02d}": float(np.quantile(v, q)) for q in qs}}


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
    log10_abs_input: dict[str, float]  # distribution of log10 |X[i, j]|, without min and max
    negative_input_share: float  # inputs with X < 0 (wastes sent to treatment)
    column_abs_sum: dict[str, float]  # sum over i of |X[i, j]|, without min and max
    loops: dict[str, float]  # strongly connected components of more than one product
    spectral_radius: float | None  # largest |eigenvalue| of X; None if ARPACK did not converge
    spectral_radius_abs: float | None  # largest eigenvalue of |X|, an upper bound on the above
    lu_fill: dict[str, float]  # nnz(L + U) / nnz(A) per SuperLU column ordering
    factor_seconds: dict[str, float]  # median of 3 SuperLU factorizations, per ordering
    same_location_share: float | None = None  # inputs whose supplier has the consumer's location
    same_sector_share: float | None = None  # the same for the sector; "" (unknown) is left out


def measure(
    technosphere: sparse.spmatrix,
    locations: list[str] | None = None,
    sectors: list[str] | None = None,
) -> Stats:
    """Structural statistics of a technosphere matrix ``A`` (production on the diagonal)."""
    a = sparse.csc_matrix(technosphere, dtype=np.float64)
    n = a.shape[0]
    a = a @ sparse.diags(1.0 / a.diagonal())  # production amount 1 in every column
    x = (sparse.identity(n, format="csc") - a).tocsc()
    x.setdiag(0.0)
    x.eliminate_zeros()
    xa = abs(x)

    _, labels = csgraph.connected_components(x, directed=True, connection="strong")
    sizes = np.bincount(labels)
    loops = sizes[sizes > 1]

    def radius(m: sparse.csc_matrix) -> float | None:
        if m.nnz == 0:
            return 0.0
        if n < 3:  # eigs needs k < n - 1
            return float(np.abs(np.linalg.eigvals(m.toarray())).max())
        try:
            eig = sla.eigs(m, k=1, which="LM", return_eigenvectors=False, tol=1e-8, maxiter=n * 10)
        except sla.ArpackNoConvergence:
            return None  # keep the other statistics of a long run
        return float(np.abs(eig).max())

    fill, seconds = {}, {}
    for order in ("COLAMD", "MMD_AT_PLUS_A"):
        times = []
        for _ in range(3):
            t0 = time.perf_counter()
            lu = sla.splu(a, permc_spec=order)
            times.append(time.perf_counter() - t0)
        fill[order] = float((lu.L.nnz + lu.U.nnz - n) / a.nnz)
        seconds[order] = float(np.median(times))

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
        inputs_per_product=_quantiles(np.diff(x.indptr)),
        consumers_per_supplier=_quantiles(np.bincount(rows, minlength=n)),
        log10_abs_input=_quantiles(np.log10(xa.data), extremes=False),
        negative_input_share=float(np.mean(x.data < 0)) if x.nnz else 0.0,
        column_abs_sum=_quantiles(xa.sum(axis=0).A1, extremes=False),
        loops={
            "components": int(loops.size),
            "largest": int(loops.max()) if loops.size else 0,
            "products_in_loops": int(loops.sum()),
        },
        spectral_radius=radius(x),
        spectral_radius_abs=radius(xa),
        lu_fill=fill,
        factor_seconds=seconds,
        same_location_share=same_share(locations),
        same_sector_share=same_share(sectors),
    )
