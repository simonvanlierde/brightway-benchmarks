"""Seeded synthetic LCA systems, written as bw_processing datapackages.

``system(profile)`` builds one. Its technosphere is ``A = I - X``: production of 1 on the
diagonal, inputs ``X`` off it. A profile picks one of two builders:

- ``tiered`` copies the structure of a real database. The ``ecoinvent`` profile is calibrated
  to ecoinvent 3.12 cut-off (``profiles/``). Products sit in a supply-chain order and mostly
  buy from earlier products. A share of inputs comes from anywhere, which closes loops.
  Suppliers are heavy-tailed hubs, and some inputs stay in the consumer's region or sector.
  Waste treatments make some inputs negative. Each product has its own unit, so amounts span
  many orders of magnitude and solvers pivot as they do on real data.
- ``random`` is the earlier generator: inputs on random rows, column sums below 0.5. Its LU
  factors fill far more than a real database's, so it is a worst case (``stress-random``).

Both builders keep ``X = T X0 T^-1``. ``T`` holds each product's signed unit (``scale``), and
every column of ``X0`` sums to less than 1. So ``I + X + X^2 + ...`` converges, and
``neumann`` computes the reference scores from it without sharing code with any solver under
test. The same arguments give the same arrays on every machine.

Building the arrays needs only numpy and scipy. ``write_datapackages`` also needs
bw_processing, so it runs in the benchmark container.
"""

from __future__ import annotations

import functools
import hashlib
import json
import math
import shutil
import time
import uuid
from collections import Counter
from dataclasses import asdict, dataclass, replace
from importlib.metadata import version
from pathlib import Path
from typing import TYPE_CHECKING, Any, NamedTuple

import numpy as np
from scipy import sparse
from scipy.sparse import csgraph
from scipy.sparse import linalg as sla

if TYPE_CHECKING:
    from numpy.typing import NDArray

# Bump when a builder or the stored reference changes. It is part of the cache key and of
# the asv `version` of benchmarks on generated data, so their old results are dropped.
# That replaces asv's hash of the benchmark code: bump it when their timed code changes too.
GENERATOR_VERSION = "3"
INPUTS_SHARE = 0.5  # random builder: upper bound on the sum of input amounts per column
NEUMANN_TOL = 1e-17  # the series stops when the rest of it is below this, relative to the demand
NEUMANN_MAX_TERMS = 5_000  # without a bound on the rest; radius 0.99 needs about 4,000
FACTORIZE_BUDGET = 900.0  # seconds of SuperLU a benchmark case may spend, half asv's timeout
MAX_COLUMN_SUM = 0.9  # tiered builder: the reference's series needs column sums below 1
# Bands of entries per supplier row for overlap_by_band, both ends included. A row's entries
# are its consumers plus its own production, so "17-64" means 16 to 63 consumers.
OVERLAP_BANDS = (
    (2, 4),
    (5, 16),
    (17, 64),
    (65, 256),
    (257, 1 << 62),
)
REFERENCE_PRODUCTS = 30  # reference scores are stored for products 0 to 29, the most MultiScores demands
PROFILES_DIR = Path(__file__).parent / "profiles"


@dataclass(frozen=True)
class Profile:
    """The shape of one synthetic system. Fields after ``builder`` apply to its builder only."""

    products: int
    flows: int  # biosphere flows
    builder: str = "tiered"
    flows_per_product: int = 3
    methods: int = 3
    # random builder
    inputs: int = 8  # upstream inputs per product, before repeated cells are dropped
    # tiered builder
    inputs_median: float = 5.0  # inputs per product are lognormal, rounded
    inputs_sigma: float = 1.34
    inputs_max: int = 410  # caps the longest input lists
    inputs_extra: float = 1.15  # more draws than inputs, for the repeated cells that are dropped
    terminal: float = 0.12  # share of products nothing buys
    hub_sigma: float = 2.75  # spread of supplier weights: higher, fewer and bigger hubs
    hub_cap: int = 1100  # most draws one supplier is expected to get
    back: float = 0.15  # share of drawn inputs from anywhere in the order: they close the loops
    same_region: float = 0.23  # share of drawn inputs from the consumer's region
    same_sector: float = 0.28  # the same for its sector
    regions: int = 20
    sectors: int = 40
    treatment: float = 0.126  # share of products that are waste treatments
    amount_sigma: float = 3.5  # lognormal spread of input amounts within a column, before units
    units: float = 0.3  # standard deviation of log10 of each product's unit
    radius: float = 0.78  # spectral radius of X
    target: str | None = None  # file in profiles/ the profile was calibrated to

    def digest(self) -> str:
        """Short hash of the profile's fields: what shapes the arrays.

        Not of the calibration file: the builders never read it, and new measurements in it
        must not drop asv's results by changing their version.
        """
        return _short_hash(asdict(self))


def _short_hash(key: object, length: int = 12) -> str:
    """Hex digest of ``key`` as sorted JSON, cut to ``length``: the form of every cache and version key."""
    return hashlib.sha256(json.dumps(key, sort_keys=True).encode()).hexdigest()[:length]


# Calibrated to the target file with measure(). Degrees, the giant loop, the negative share,
# the radius and locality land within a few percent; tests/test_measure.py checks them.
# Two gaps remain:
# - LU fill is COLAMD 323 and MMD_AT_PLUS_A 99, against 175 and 76. Fill follows the size of
#   the giant loop. At 64%, no hub, locality or nested-locality setting lowered it.
# - The top of log10 |x| is narrower: q99 0.3 against 4.8. Wider units raise fill further.
ECOINVENT = Profile(products=26_533, flows=4_000, target="ecoinvent-3.12-cutoff.json")

# NOTE: only `ecoinvent` is calibrated (to its file in profiles/). The others scale it, or
# keep the random builder where no structure is known.
PROFILES: dict[str, Profile] = {
    # More loops, so 200 products get close to ecoinvent's radius (see MAX_COLUMN_SUM).
    "smoke": replace(ECOINVENT, products=200, flows=30, regions=4, sectors=8, back=0.3, target=None),
    "ecoinvent": ECOINVENT,
    # EXIOBASE 3 product by product: 9,800 sectors (49 regions x 200 products), much denser.
    "exiobase": Profile(products=9_800, flows=1_100, builder="random", inputs=400),
    # #131's large Monte Carlo case is 100k products (at 2% fill there, far denser than this).
    "mc100k": replace(ECOINVENT, products=100_000),
    # The regionalised system from Brightcon 2026 contribution 59: 250k x 250k.
    "regional": replace(ECOINVENT, products=250_000),
    # The earlier generator at about ecoinvent's size: L+U fills to about 60% of a dense matrix.
    "stress-random": Profile(products=20_000, flows=4_000, builder="random", inputs=8),
}


def profile(name: str, **overrides: object) -> Profile:
    """A registered profile, with ``overrides`` (such as ``products=8_000``) applied."""
    return replace(PROFILES[name], **overrides)


class Packages(NamedTuple):
    """What a benchmark loads: the datapackages, the reference scores and the unit scale."""

    inventory: Any
    methods: list[Any]
    reference: list[list[float]]
    scale: NDArray[np.float64]


@dataclass(frozen=True)
class System:
    """One synthetic system as coordinate arrays, with bw2calc's sign convention.

    Technosphere inputs are stored as ``X[i, j]`` with ``flip`` set, as bw2data writes
    them, so the matrix bw2calc builds is ``A = I - X``. ``scale`` is each product's signed
    unit: ``X = T X0 T^-1`` with ``X0 >= 0`` and ``T = diag(scale)``.
    """

    name: str
    profile: Profile
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
    scale: NDArray[np.float64]
    uncertain: bool = False
    region: NDArray[np.int64] | None = None  # tiered builder: each product's region and sector
    sector: NDArray[np.int64] | None = None

    @property
    def flow_offset(self) -> int:
        """Biosphere flow ids start here, so they never collide with product ids."""
        return self.profile.products

    def technosphere(self) -> sparse.csc_matrix:
        """The technosphere matrix bw2calc builds from this system."""
        n = self.profile.products
        signed = np.where(self.tech_flip, -self.tech_data, self.tech_data)
        return sparse.csc_matrix((signed, (self.tech_rows, self.tech_cols)), shape=(n, n))

    def biosphere(self) -> sparse.csc_matrix:
        """Biosphere matrix with flows renumbered from 0."""
        shape = (self.profile.flows, self.profile.products)
        return sparse.csc_matrix((self.bio_data, (self.bio_rows - self.flow_offset, self.bio_cols)), shape=shape)

    @functools.cached_property
    def reference(self) -> list[list[float]]:
        """Score of one unit of each of products 0 to 29, per method: ``reference[p][m]``.

        This is what every Brightway result is checked against. Computed once.
        """
        return self.reference_scores()

    def reference_scores(self, products: int = REFERENCE_PRODUCTS) -> list[list[float]]:
        """Score of one unit of each of the first ``products`` products, per method."""
        n = self.profile.products
        inputs = sparse.identity(n, format="csr") - self.technosphere().tocsr()
        supply = neumann(inputs, np.eye(n, min(products, n)), scale=self.scale)
        inventory = self.biosphere() @ supply
        return [
            [float(inventory[f - self.flow_offset, p] @ c) for f, c in zip(self.cf_flows, self.cf_data, strict=True)]
            for p in range(supply.shape[1])
        ]

    def float32_reference(self) -> float:
        """``reference_scores(1)[0][0]`` with every amount rounded to float32, as bw2data's processed arrays hold them.

        bw_processing 1.6 stores amounts as float32 (brightway-lca/bw_processing#112), which moves
        bw2data's score by 3e-9 at smoke size and 5.7e-8 at the ecoinvent size. Against this
        reference it is off by about 1e-15. Drop it once #112 is fixed.
        """

        def f32(a: NDArray[np.float64]) -> NDArray[np.float64]:
            return a.astype(np.float32).astype(np.float64)

        rounded = replace(
            self, tech_data=f32(self.tech_data), bio_data=f32(self.bio_data), cf_data=[f32(c) for c in self.cf_data]
        )
        return rounded.reference_scores(1)[0][0]

    def datapackages(self) -> Path:
        """Folder of this system's datapackages in the cache, written on first use.

        Written to a temporary folder and renamed, so a run that dies half-way, or two runs
        at once, never leave a folder that looks complete.
        """
        folder = cache_folder(self.name, self.profile, seed=self.seed, uncertain=self.uncertain)
        if folder.exists():
            return folder
        # A run that died half-way left its folder; one older than a day is no live run's.
        for stale in folder.parent.glob(f"{folder.name}.tmp-*"):
            if time.time() - stale.stat().st_mtime > 86_400:
                shutil.rmtree(stale, ignore_errors=True)
        tmp = folder.with_name(f"{folder.name}.tmp-{uuid.uuid4().hex}")  # PIDs repeat across containers
        write_datapackages(self, tmp)
        try:
            tmp.rename(folder)
        except OSError:
            if not folder.exists():
                raise
            shutil.rmtree(tmp)  # another run finished first
        return folder

    def packages(self) -> Packages:
        """The datapackages loaded with bw_processing, generated on first use."""
        return load(self.datapackages())

    def bw2data(self, db: str = "synth", bio: str = "bio") -> tuple[dict, dict, list[list]]:
        """This system as the dicts ``bw2data.Database.write`` and ``Method.write`` take."""
        return as_bw2data(self, db=db, bio=bio)


def system(name: str, *, seed: int = 0, uncertain: bool = False, **overrides: object) -> System:
    """Build the system of profile ``name``. Same arguments, same arrays (and the same object).

    ``uncertain`` gives technosphere inputs a distribution in the datapackages, for Monte
    Carlo. ``overrides`` change profile fields, such as ``products=8_000``. The arrays are
    read-only, because repeated calls share them.
    """
    return _build(name, profile(name, **overrides), seed, uncertain)


# Keyed on the resolved profile, not its name, so an edited profile never returns a stale system.
@functools.lru_cache(maxsize=4)  # benchmark setups ask for the same system before every sample
def _build(name: str, p: Profile, seed: int, uncertain: bool) -> System:  # noqa: FBT001
    rng = np.random.default_rng(seed)
    n = p.products
    region = sector = None
    match p.builder:
        case "tiered":
            rows, cols, amounts, scale, region, sector = _tiered(p, rng)
        case "random":
            rows, cols, amounts = _random(p, rng)
            scale = np.ones(n)
        case _:
            msg = f"unknown builder {p.builder!r}"
            raise ValueError(msg)

    diag = np.arange(n, dtype=np.int64)
    tech_rows = np.concatenate([diag, rows])
    tech_cols = np.concatenate([diag, cols])
    tech_data = np.concatenate([np.ones(n), amounts])
    tech_flip = np.concatenate([np.zeros(n, dtype=bool), np.ones(rows.size, dtype=bool)])

    m = p.flows_per_product
    bio_cols = np.repeat(diag, m)
    bio_flows = rng.integers(0, p.flows, size=n * m, dtype=np.int64)
    # Every product emits flow 0 and every method counts it, so every score is above 0.
    bio_flows[::m] = 0
    _, first = np.unique(bio_flows * n + bio_cols, return_index=True)
    bio_rows = bio_flows[first] + n
    bio_cols = bio_cols[first]
    # Emissions per unit of product: in the product's own unit, and negative for a treatment.
    bio_data = rng.lognormal(0.0, 1.0, size=bio_rows.size) / scale[bio_cols]

    cf_flows, cf_data = [], []
    for _ in range(p.methods):
        flows = np.sort(rng.choice(np.arange(1, p.flows), size=max(1, p.flows // 10) - 1, replace=False))
        flows = np.concatenate([[0], flows]).astype(np.int64)
        cf_flows.append(flows + n)
        cf_data.append(rng.lognormal(0.0, 1.0, size=flows.size))

    for a in (tech_rows, tech_cols, tech_data, tech_flip, bio_rows, bio_cols, bio_data, scale, *cf_flows, *cf_data):
        a.setflags(write=False)
    return System(
        name,
        p,
        seed,
        tech_rows,
        tech_cols,
        tech_data,
        tech_flip,
        bio_rows,
        bio_cols,
        bio_data,
        cf_flows,
        cf_data,
        scale,
        uncertain,
        region,
        sector,
    )


def skip_unless_factorizable(name: str, *, pardiso: bool, factorizations: int = 1) -> None:
    """Skip a case whose SuperLU or UMFPACK factorizations of profile ``name`` would overrun.

    The estimate: 43 s per factorization at 18k products of the tiered structure, growing
    about as n^3.6 (one thread, measured 2026-10-13); half the 30-minute asv timeout is the
    budget. PyPardiso is far faster, so it is never skipped. asv records the skip as a gap.
    """
    seconds = factorizations * 43.0 * (profile(name).products / 18_000) ** 3.6
    if not pardiso and seconds > FACTORIZE_BUDGET:
        msg = f"{name}: {factorizations} factorizations would take about {seconds / 60:.0f} min without PyPardiso"
        raise NotImplementedError(msg)


def packages(name: str, *, seed: int = 0, uncertain: bool = False, **overrides: object) -> Packages:
    """``system(...).packages()``, without building the arrays when the cache has them."""
    folder = cache_folder(name, profile(name, **overrides), seed=seed, uncertain=uncertain)
    if not folder.exists():
        folder = system(name, seed=seed, uncertain=uncertain, **overrides).datapackages()
    return load(folder)


def _random(p: Profile, rng: np.random.Generator) -> tuple[NDArray, NDArray, NDArray]:
    """``p.inputs`` inputs per column on uniformly random rows, summing to less than 0.5."""
    n, k = p.products, p.inputs
    cols = np.repeat(np.arange(n, dtype=np.int64), k)
    rows = rng.integers(0, n, size=n * k, dtype=np.int64)
    rows, cols = _off_diagonal_once(rows, cols, n)
    return rows, cols, rng.uniform(0.0, INPUTS_SHARE / k, size=rows.size)


def _off_diagonal_once(rows: NDArray, cols: NDArray, n: int) -> tuple[NDArray, NDArray]:
    """Drop self-loops (the diagonal holds production only) and repeated cells, keeping the first."""
    keep = rows != cols
    _, first = np.unique(rows[keep] * n + cols[keep], return_index=True)
    return rows[keep][first], cols[keep][first]


def _draw(
    rng: np.random.Generator, consumers: NDArray, weight: NDArray, group: NDArray, back: float
) -> tuple[NDArray, NDArray]:
    """One supplier per consumer, weighted by ``weight``, from the consumer's ``group``.

    A ``back`` share may come from anywhere in the group; the rest from earlier in the
    order. Returns the suppliers and whether each draw found one (the first product of a
    group has nobody before it).
    """
    n = weight.size
    order = np.lexsort((np.arange(n), group))  # by group, then by position
    pos = np.empty(n, dtype=np.int64)
    pos[order] = np.arange(n)
    starts = np.searchsorted(group[order], np.arange(group.max() + 2))
    cum = np.concatenate([[0.0], np.cumsum(weight[order])])
    g = group[consumers]
    lo = cum[starts[g]]
    hi = np.where(rng.random(consumers.size) < back, cum[starts[g + 1]], cum[pos[consumers]])
    at = lo + rng.random(consumers.size) * (hi - lo)
    pick = np.clip(np.searchsorted(cum, at, side="right") - 1, 0, n - 1)
    return order[pick], hi > lo


def _tiered(p: Profile, rng: np.random.Generator) -> tuple[NDArray, ...]:
    """The supply-chain structure the module docstring describes, scaled to ``p.radius`` at most.

    Position 0 is the most basic product and position n - 1 the most finished one; product
    ids run the other way, so the reference products 0 to 29 have the deepest chains.
    """
    n = p.products
    k = np.minimum(np.rint(rng.lognormal(np.log(p.inputs_median), p.inputs_sigma, n)), p.inputs_max)
    sells = rng.random(n) >= p.terminal
    sells[n - min(n, REFERENCE_PRODUCTS) :] = True

    # Every product that sells has at least one consumer later in the order, weighted by
    # that consumer's inputs: most products feed one or two others.
    suppliers = np.flatnonzero(sells[:-1])
    cum_k = np.concatenate([[0.0], np.cumsum(k)])
    at = cum_k[suppliers + 1] + rng.random(suppliers.size) * (cum_k[-1] - cum_k[suppliers + 1])
    consumers = np.clip(np.searchsorted(cum_k, at, side="right") - 1, 0, n - 1)
    left = np.rint(np.maximum(k - np.bincount(consumers, minlength=n), 0) * p.inputs_extra).astype(np.int64)

    # The other inputs go to heavy-tailed hubs, capped so no supplier expects more than hub_cap.
    cols = np.repeat(np.arange(n, dtype=np.int64), left)
    weight = rng.lognormal(0.0, p.hub_sigma, n) * sells
    for _ in range(5):
        weight = np.minimum(weight, p.hub_cap * weight.sum() / max(cols.size, 1))
    pool = rng.random(cols.size)
    pool = np.where(pool < p.same_region, 1, np.where(pool < p.same_region + p.same_sector, 2, 0))
    groups = (np.zeros(n, dtype=np.int64), rng.integers(0, p.regions, n), rng.integers(0, p.sectors, n))
    rows = np.empty(cols.size, dtype=np.int64)
    found = np.empty(cols.size, dtype=bool)
    for i, group in enumerate(groups):
        m = pool == i
        rows[m], found[m] = _draw(rng, cols[m], weight, group, p.back)

    rows = np.concatenate([suppliers, rows[found]])
    cols = np.concatenate([consumers, cols[found]])
    rows, cols = _off_diagonal_once(rows, cols, n)

    # Amounts free of units: lognormal, each column summing to 1, then all scaled to the radius.
    amounts = rng.lognormal(0.0, p.amount_sigma, rows.size)
    amounts /= np.bincount(cols, weights=amounts, minlength=n)[cols]
    # A small system whose loops are too weak stays below the radius rather than break that bound.
    rho = spectral_radius(sparse.csc_matrix((amounts, (rows, cols)), shape=(n, n)))
    if rho is None:
        msg = f"ARPACK did not converge on {p}: the radius cannot be set"
        raise ArithmeticError(msg)
    factor = MAX_COLUMN_SUM if rho * MAX_COLUMN_SUM <= p.radius else p.radius / rho
    # Rounded, so a last-bit difference in ARPACK between machines cannot change the arrays.
    amounts *= float(f"{factor:.9g}")

    sign = np.where(rng.random(n) < p.treatment, -1.0, 1.0)
    sign[n - min(n, REFERENCE_PRODUCTS) :] = 1.0  # reference products are not treatments
    scale = sign * 10.0 ** rng.normal(0.0, p.units, n)
    ids = n - 1 - np.arange(n)  # position to product id
    order = np.argsort(ids)
    region, sector = groups[1][order], groups[2][order]
    return ids[rows], ids[cols], scale[rows] * amounts / scale[cols], scale[order], region, sector


def spectral_radius(m: sparse.csc_matrix | sparse.csr_matrix) -> float | None:
    """Largest ``|eigenvalue|`` of ``m``; None if ARPACK did not converge."""
    n = m.shape[0]
    if m.nnz == 0:
        return 0.0
    if n < 3:  # eigs needs k < n - 1
        return float(np.abs(np.linalg.eigvals(m.toarray())).max())
    try:
        eig = sla.eigs(m, k=1, which="LM", return_eigenvectors=False, tol=1e-8, maxiter=n * 10, v0=np.ones(n))
    except sla.ArpackNoConvergence:
        return None
    return float(np.abs(eig).max())


def neumann(
    inputs: sparse.spmatrix, demand: NDArray[np.float64], scale: NDArray[np.float64] | None = None
) -> NDArray[np.float64]:
    """Solve ``(I - inputs) x = demand`` as the series ``demand + inputs @ demand + ...``.

    It shares no code with any solver under test and needs no factorization, so it stays
    cheap at every size. ``scale`` is the system's signed unit per product, in the matrix's
    order; the series runs on the matrix without units.

    When that matrix's largest column sum ``s`` is below 1, the rest of the series is at most
    ``|term| s / (1 - s)``. The series stops once that is below ``NEUMANN_TOL`` of the
    demand: about 150 terms at ``s = 0.78``. A Monte Carlo draw can push a column sum past 1.
    Then the series stops once one term is below that tolerance, and raises if that takes
    more than ``NEUMANN_MAX_TERMS`` terms.
    """
    t = np.ones(inputs.shape[0]) if scale is None else np.asarray(scale, dtype=np.float64)
    shape = (-1,) + (1,) * (np.ndim(demand) - 1)
    x0 = sparse.diags(1 / t) @ sparse.csr_matrix(inputs) @ sparse.diags(t)
    s = float(abs(x0).sum(axis=0).max())
    term = demand / t.reshape(shape)
    x = term.copy()
    if s < 1:
        stop = NEUMANN_TOL * np.abs(term).sum(axis=0) * (1 - s) / max(s, 1e-300)
        terms = 1 + math.ceil(math.log(NEUMANN_TOL * (1 - s) / s) / math.log(s)) if s > 0 else 0
    else:
        stop = NEUMANN_TOL * np.abs(term).sum(axis=0)
        terms = NEUMANN_MAX_TERMS
    for _ in range(terms + 1):
        if np.all(np.abs(term).sum(axis=0) <= stop):
            return x * t.reshape(shape)
        term = x0 @ term
        x += term
    msg = "Neumann series did not reach its tolerance"
    raise ArithmeticError(msg)


def neumann_score(lca: Any, scale: NDArray[np.float64] | None = None) -> float:  # noqa: ANN401 - a bw2calc LCA
    """The score of the matrices ``lca`` has loaded, solved by ``neumann`` instead of its solver.

    ``scale`` is the system's unit per product in ``lca``'s matrix order.
    """
    a = lca.technosphere_matrix
    supply = neumann(sparse.identity(a.shape[0], format="csr") - a, lca.demand_array, scale=scale)
    return float((lca.characterization_matrix @ lca.biosphere_matrix @ supply).sum())


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


def write_datapackages(system: System, folder: Path) -> Path:
    """Write ``system`` as bw_processing datapackages under ``folder``.

    ``inventory/`` holds the technosphere and biosphere, and ``method-<i>/`` one
    characterization each, with the ``identifier`` MultiLCA filters on. They are separate
    because a plain ``LCA`` sums every characterization it is given. With ``system.uncertain``,
    technosphere inputs get a normal distribution with a 10% standard deviation, for
    Monte Carlo. ``reference.json`` holds the reference scores and ``scale.npy`` the units.
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
    if system.uncertain:
        distributions = np.zeros(system.tech_data.size, dtype=bwp.UNCERTAINTY_DTYPE)
        for name in ("shape", "minimum", "maximum"):
            distributions[name] = np.nan
        distributions["loc"] = system.tech_data
        distributions["uncertainty_type"] = np.where(system.tech_flip, 3, 0)  # 3: normal
        distributions["scale"] = np.where(system.tech_flip, 0.1 * np.abs(system.tech_data), np.nan)

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

    meta = {
        "profile": system.name,
        "shape": asdict(system.profile),
        "seed": system.seed,
        "reference_scores": system.reference,
    }
    (folder / "reference.json").write_text(json.dumps(meta, indent=2))
    np.save(folder / "scale.npy", system.scale)
    return folder


def data_root() -> Path:
    """Where generated datapackages are cached: ``~/.cache/bwbench`` (under ``.asv/`` in the box)."""
    return Path.home() / ".cache" / "bwbench"


def cache_folder(name: str, p: Profile, *, seed: int, uncertain: bool, bwp_version: str | None = None) -> Path:
    """Cache folder for one system: a new one whenever anything that shapes the files changes."""
    bwp_version = bwp_version or version("bw_processing")
    key = [p.digest(), seed, uncertain, GENERATOR_VERSION, bwp_version]
    return data_root() / f"{name}-{_short_hash(key)}"


def profile_version() -> str:
    """The asv ``version`` of benchmarks on generated data: changes when any profile does.

    It covers every registered profile, not the ones a run selects, so runs over different
    sizes share one history. asv drops results whose version differs.
    """
    return f"{GENERATOR_VERSION}-{_short_hash(sorted((n, p.digest()) for n, p in PROFILES.items()), 8)}"


def load(folder: Path) -> Packages:
    """The inventory and method datapackages, the reference scores and the units in ``folder``."""
    import bw_processing as bwp  # noqa: PLC0415

    def read(name: str) -> object:
        return bwp.load_datapackage(bwp.generic_directory_filesystem(dirpath=folder / name))

    meta = json.loads((folder / "reference.json").read_text())
    methods = [read(f"method-{i}") for i in range(meta["shape"]["methods"])]
    return Packages(read("inventory"), methods, meta["reference_scores"], np.load(folder / "scale.npy"))


def as_bw2data(system: System, db: str = "synth", bio: str = "bio") -> tuple[dict, dict, list[list]]:
    """The same system as the dicts ``bw2data.Database.write`` and ``Method.write`` take.

    Returns the biosphere database, the technosphere database, and one CF list per
    method. Product ``i`` has code ``p<i>``; flow ``j`` has code ``f<j>``.
    """
    off = system.flow_offset
    biosphere = {
        (bio, f"f{j}"): {"name": f"flow {j}", "unit": "kilogram", "type": "emission", "categories": ("air",)}
        for j in range(system.profile.flows)
    }
    exchanges: list[list[dict]] = [[] for _ in range(system.profile.products)]
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
    spectral_radius: float | None  # largest |eigenvalue| of X; None if ARPACK did not converge
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


def measure(
    technosphere: sparse.spmatrix,
    locations: list[str] | None = None,
    sectors: list[str] | None = None,
    *,
    repeats: int = 3,
) -> Stats:
    """Structural statistics of a technosphere matrix ``A`` (production on the diagonal).

    ``repeats`` SuperLU factorizations per ordering give the median time, for A and for A^T
    (keys ending in ``(A^T)``); 0 skips them, and the fill with them.
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

    fill, seconds, fill_no_pivoting, pivots = {}, {}, {}, {}
    # A^T too: bw2calc's decompose_technosphere factorizes A, scipy's spsolve on CSR input A^T.
    for m, suffix in ((a, ""), (a.T.tocsc(), " (A^T)")) if repeats else ():
        for order in ("COLAMD", "MMD_AT_PLUS_A"):
            times = []
            for _ in range(repeats):
                t0 = time.perf_counter()
                lu = sla.splu(m, permc_spec=order)
                times.append(time.perf_counter() - t0)
            fill[order + suffix] = _lu_fill(lu, m)
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
