"""The registered profiles: the shape of each benchmark system, and where their files are cached.

Standard library only, so a script that lists the profiles (``scripts/run_crate.py``) needs
neither numpy nor scipy. ``bwbench.synth`` builds the systems.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass, replace
from pathlib import Path

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
    # Keep fitted precision: crossing an integer input count changes the subsequent random draws.
    inputs_median: float = 4.293068301720509  # rounded lognormal quantiles within family-size bands
    inputs_sigma: float = 1.560981997653939
    inputs_max: int = 410  # caps the longest input lists
    inputs_extra: float = 1.1568092697778913  # more draws than inputs, for the repeated cells that are dropped
    terminal: float = 0.1524486748309  # share of products nothing buys
    hub_sigma: float = 2.774336543482854  # spread of supplier weights: higher, fewer and bigger hubs
    hub_cap: int = 556  # most draws one supplier is expected to get
    back: float = 0.21584040362970142  # share of drawn inputs from anywhere in the order: they close the loops
    same_region: float = 0.17242732136949018  # share of drawn inputs from the consumer's region
    same_sector: float = 0.35546934561276256  # the same for its sector
    regions: int = 28
    sectors: int = 40
    # Activity families: one activity offered in several regions, its members neighbours in the
    # order. Every member copies its family's first member's inputs; a supplier with a member in
    # the consumer's region is swapped for that member with chance family_local.
    family_zipf: float = 1.8935567175472885  # Zipf exponent of family sizes: lower, more and bigger families
    family_max: int = 200
    family_local: float = 0.3467999994573744
    family_hub_sales: float = 0.1965347464979818  # see _sell_locally
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
        return short_hash(asdict(self))


def short_hash(key: object, length: int = 12) -> str:
    """Hex digest of ``key`` as sorted JSON, cut to ``length``: the form of every cache and version key."""
    return hashlib.sha256(json.dumps(key, sort_keys=True).encode()).hexdigest()[:length]


# tests/test_measure.py checks degrees, loops, signs, radius, locality and fill over seeds 0 to 3.
# Input magnitudes still have a narrower upper tail than the calibration data.
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
    # The real systems (bwbench.useeio, bwbench.bafu). Their data come from pinned archives, so
    # the generator's version says nothing about them and `profile_version` leaves them out.
    "useeio": Profile(products=388, flows=1_871, builder="useeio", methods=3, target="USEEIO-1.1"),
    "bafu": Profile(products=11_747, flows=2_678, builder="bafu", methods=3, target="BAFU-2025-v2"),
}


def profile(name: str, **overrides: object) -> Profile:
    """A registered profile, with ``overrides`` (such as ``products=8_000``) applied."""
    return replace(PROFILES[name], **overrides)


def data_root() -> Path:
    """Where generated datapackages are cached: ``$XDG_CACHE_HOME/bwbench``, by default ``~/.cache/bwbench``.

    The box sets XDG_CACHE_HOME under ``.asv/``, so the cache outlives its per-run home.
    """
    return Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "bwbench"
