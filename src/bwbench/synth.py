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

Building the arrays needs only numpy and scipy. Writing them (``datapackages``) also needs
bw_processing, so it runs in the benchmark container. ``bwbench.shapes`` holds the profiles,
``bwbench.matrices`` the arrays' container and the reference, ``bwbench.stats`` the statistics
the profiles are calibrated on.
"""

from __future__ import annotations

import functools
import shutil
import time
import uuid
from importlib.metadata import version
from typing import TYPE_CHECKING

import numpy as np
from scipy import sparse, special

from bwbench import bafu, useeio
from bwbench.matrices import REFERENCE_PRODUCTS, Packages, System, load, write_datapackages
from bwbench.shapes import PROFILES, Profile, data_root, profile, short_hash
from bwbench.stats import spectral_radius

if TYPE_CHECKING:
    from pathlib import Path

    from numpy.typing import NDArray

# Bump when a builder or the stored reference changes. It is part of the cache key and of
# the asv `version` of benchmarks on generated data, so their old results are dropped.
# That replaces asv's hash of the benchmark code: bump it when their timed code changes too.
# tests/test_synth.py pins a hash of system("smoke")'s arrays to it: update both together.
GENERATOR_VERSION = "5"
INPUTS_SHARE = 0.5  # random builder: upper bound on the sum of input amounts per column
MAX_COLUMN_SUM = 0.9  # tiered builder: the reference's series needs column sums below 1
# The builders that read a real system from a pinned archive, by profile builder name.
ARCHIVES = {"useeio": useeio.system, "bafu": bafu.system}


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
    if p.builder in ARCHIVES:
        if uncertain:
            msg = f"{p.target} has no uncertainty here: its Monte Carlo case is not defined"
            raise NotImplementedError(msg)
        return ARCHIVES[p.builder](p, seed)
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

    shared = (tech_rows, tech_cols, tech_data, tech_flip, bio_rows, bio_cols, bio_data, scale, *cf_flows, *cf_data)
    for a in (*shared, *(g for g in (region, sector) if g is not None)):
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


def factorize_seconds(name: str) -> float:
    """Estimated seconds for one SuperLU factorization of profile ``name``, one thread.

    Tiered structure: 43 s at 18k products, growing about as n^3.6 (measured 2026-10-13).
    The random builder fills L+U far more: 17 s at 8k products, growing about as n^3.1
    (stress-random and exiobase shapes, measured 2026-11-11).
    """
    p = profile(name)
    if p.builder == "random":
        return 17.0 * (p.products / 8_000) ** 3.1
    return 43.0 * (p.products / 18_000) ** 3.6


def skip_unless_factorizable(name: str, *, pardiso: bool, timeout: float, factorizations: int = 1) -> None:
    """Skip a case whose SuperLU or UMFPACK factorizations of profile ``name`` would overrun.

    ``timeout`` is the case's asv timeout in seconds: a case estimated past it skips instead
    of timing out. PyPardiso is far faster, so it is never skipped. asv records the skip as a gap.
    """
    seconds = factorizations * factorize_seconds(name)
    if not pardiso and seconds > timeout:
        msg = f"{name}: {factorizations} factorizations would take about {seconds / 60:.0f} min without PyPardiso"
        raise NotImplementedError(msg)


def datapackages(system: System) -> Path:
    """Folder of ``system``'s datapackages in the cache, written on first use.

    Written to a temporary folder and renamed, so a run that dies half-way, or two runs
    at once, never leave a folder that looks complete.
    """
    folder = cache_folder(system.name, system.profile, seed=system.seed, uncertain=system.uncertain)
    if folder.exists():
        return folder
    # A run that died half-way left its folder; one older than a day is no live run's.
    for stale in folder.parent.glob(f"{folder.name}.tmp-*"):
        if time.time() - stale.stat().st_mtime > 86_400:
            shutil.rmtree(stale, ignore_errors=True)
    tmp = folder.with_name(f"{folder.name}.tmp-{uuid.uuid4().hex}")  # PIDs repeat across containers
    write_datapackages(system, tmp)
    try:
        tmp.rename(folder)
    except OSError:
        if not folder.exists():
            raise
        shutil.rmtree(tmp)  # another run finished first
    return folder


def packages(name: str, *, seed: int = 0, uncertain: bool = False, **overrides: object) -> Packages:
    """``load(datapackages(system(...)))``, without building the arrays when the cache has them."""
    folder = cache_folder(name, profile(name, **overrides), seed=seed, uncertain=uncertain)
    if not folder.exists():
        folder = datapackages(system(name, seed=seed, uncertain=uncertain, **overrides))
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


def _families(p: Profile, rng: np.random.Generator, n: int) -> tuple[NDArray, NDArray]:
    """Stratified capped-Zipf family sizes, shuffled into the supply-chain order."""
    values = np.arange(1, p.family_max + 1)
    probabilities = values.astype(float) ** (-p.family_zipf) / special.zeta(p.family_zipf, 1)
    probabilities[-1] = 1 - probabilities[:-1].sum()  # the cap includes the upper tail
    count = max(1, round(n / (values @ probabilities)))
    sizes = np.searchsorted(np.cumsum(probabilities), (np.arange(count) + 0.5) / count) + 1
    remaining = n - sizes.sum()
    if remaining > 0:
        sizes = np.concatenate([sizes, np.minimum(p.family_max, np.arange(remaining, 0, -p.family_max))])
    else:
        sizes = sizes[: np.searchsorted(np.cumsum(sizes), n) + 1]
        sizes[-1] -= sizes.sum() - n
    sizes = rng.permutation(sizes)
    return np.repeat(np.arange(sizes.size), sizes), np.concatenate([[0], np.cumsum(sizes)[:-1]])


def _family_inputs(p: Profile, rng: np.random.Generator, fam: NDArray) -> NDArray:
    """Shuffle fixed lognormal quantiles within family-size bands to control variation between seeds.

    These are finite empirical distributions: a band with few families has a shorter tail.
    """
    bands = np.floor(np.log2(np.bincount(fam))).astype(np.int64)
    counts = np.empty(bands.size)
    for band in np.unique(bands):
        mask = bands == band
        quantiles = rng.permutation((np.arange(mask.sum()) + 0.5) / mask.sum())
        counts[mask] = np.minimum(
            np.rint(np.exp(np.log(p.inputs_median) + p.inputs_sigma * special.ndtri(quantiles))), p.inputs_max
        )
    return counts[fam]


def _copy_templates(
    rows: NDArray, cols: NDArray, fam: NDArray, first: NDArray, region: NDArray, p: Profile, rng: np.random.Generator
) -> tuple[NDArray, NDArray]:
    """Replace every family member's inputs with its first member's, made local (see ``Profile``)."""
    n = fam.size
    template = first[fam[cols]] == cols
    rows, cols = rows[template], cols[template]
    reps = np.bincount(fam)[fam[cols]]
    supplier = np.repeat(rows, reps)
    member = np.repeat(cols, reps) + np.arange(reps.sum()) - np.repeat(np.cumsum(reps) - reps, reps)
    key = fam * p.regions + region
    order = np.argsort(key, kind="stable")
    want = fam[supplier] * p.regions + region[member]
    at = np.minimum(np.searchsorted(key[order], want), n - 1)
    local = (key[order][at] == want) & (rng.random(supplier.size) < p.family_local) & (member != first[fam[member]])
    return np.where(local, order[at], first[fam[supplier]]), member


def _sell_locally(
    rows: NDArray, cols: NDArray, fam: NDArray, first: NDArray, rank: NDArray, p: Profile, rng: np.random.Generator
) -> tuple[NDArray, NDArray]:
    """Give each later family member that nobody buys from a buyer later in the order.

    The buyer is a member of the same rank (its region's market) or, with chance
    ``family_hub_sales``, that member's family's first member (the same market, global).
    Without this, most members sell to nobody and none sits in a loop.
    """
    n = rank.size
    idle = np.flatnonzero((np.bincount(rows, minlength=n) == 0) & (rank > 0))
    order = np.lexsort((np.arange(n), rank))  # by rank, then position
    starts = np.searchsorted(rank[order], np.arange(rank.max() + 2))
    pos = np.empty(n, dtype=np.int64)
    pos[order] = np.arange(n)
    lo, hi = pos[idle] + 1, starts[rank[idle] + 1]
    ok = lo < hi
    buyer = order[lo[ok] + (rng.random(ok.sum()) * (hi[ok] - lo[ok])).astype(np.int64)]
    buyer = np.where(rng.random(buyer.size) < p.family_hub_sales, first[fam[buyer]], buyer)
    return np.concatenate([rows, idle[ok]]), np.concatenate([cols, buyer])


def _tiered(p: Profile, rng: np.random.Generator) -> tuple[NDArray, ...]:
    """The supply-chain structure the module docstring describes, scaled to ``p.radius`` at most.

    Position 0 is the most basic product and position n - 1 the most finished one; product
    ids run the other way, so the reference products 0 to 29 have the deepest chains.
    """
    n = p.products
    fam, first = _families(p, rng, n)
    k = _family_inputs(p, rng, fam)
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
    rank = np.arange(n) - first[fam]  # members of a family get distinct regions, up to p.regions
    # Later members take regions 1, 2, ... in every family, so a member finds its local supplier;
    # first members (global, or RoW) spread over all regions.
    region = np.where(rank > 0, rank % p.regions, rng.integers(0, p.regions, n))
    groups = (np.zeros(n, dtype=np.int64), region, rng.integers(0, p.sectors, fam[-1] + 1)[fam])
    rows = np.empty(cols.size, dtype=np.int64)
    found = np.empty(cols.size, dtype=bool)
    for i, group in enumerate(groups):
        m = pool == i
        rows[m], found[m] = _draw(rng, cols[m], weight, group, p.back)

    rows, cols = rows[found], cols[found]
    rows = np.concatenate([suppliers, rows])
    cols = np.concatenate([consumers, cols])
    rows, cols = _off_diagonal_once(rows, cols, n)
    rows, cols = _copy_templates(rows, cols, fam, first, region, p, rng)
    rows, cols = _sell_locally(rows, cols, fam, first, rank, p, rng)
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


def many_groups(n: int) -> object:
    """An in-memory bw_processing datapackage with ``n`` one-entry resource groups on the diagonal."""
    import bw_processing as bwp  # noqa: PLC0415 - only the container has it

    dp = bwp.create_datapackage()
    for i in range(n):
        idx = np.array([(i, i)], dtype=bwp.INDICES_DTYPE)
        dp.add_persistent_vector(matrix="technosphere_matrix", name=f"g{i}", indices_array=idx, data_array=np.ones(1))
    return dp


def cache_folder(name: str, p: Profile, *, seed: int, uncertain: bool, bwp_version: str | None = None) -> Path:
    """Cache folder for one system: a new one whenever anything that shapes the files changes."""
    bwp_version = bwp_version or version("bw_processing")
    key = [p.digest(), seed, uncertain, GENERATOR_VERSION, bwp_version]
    return data_root() / f"{name}-{short_hash(key)}"


def profile_version() -> str:
    """The asv ``version`` of benchmarks on generated data: changes when any profile does.

    It covers every registered profile, not the ones a run selects, so runs over different
    sizes share one history. asv drops results whose version differs.
    """
    generated = sorted((n, p.digest()) for n, p in PROFILES.items() if p.builder not in ARCHIVES)
    return f"{GENERATOR_VERSION}-{short_hash(generated, 8)}"
