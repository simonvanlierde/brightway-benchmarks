"""A benchmark system as coordinate arrays, its reference scores and its files.

``System`` holds one system, synthetic (``bwbench.synth``) or read from a real archive
(``bwbench.useeio``, ``bwbench.bafu``). ``neumann`` computes the reference scores without
sharing code with any solver under test. ``write_datapackages`` also needs bw_processing, so
it runs in the benchmark container.
"""

from __future__ import annotations

import functools
import json
import math
from dataclasses import asdict, dataclass, replace
from typing import TYPE_CHECKING, Any, NamedTuple

import numpy as np
from scipy import sparse
from scipy.sparse import linalg as sla

if TYPE_CHECKING:
    from pathlib import Path

    from numpy.typing import NDArray

    from bwbench.shapes import Profile

NEUMANN_TOL = 1e-17  # the series stops when the rest of it is below this, relative to the demand
NEUMANN_MAX_TERMS = 5_000  # without a bound on the rest; radius 0.99 needs about 4,000
REFERENCE_PRODUCTS = 30  # reference scores are stored for products 0 to 29, the most MultiScores demands


class Packages(NamedTuple):
    """What a benchmark loads: the datapackages, the reference scores and the unit scale."""

    inventory: Any
    methods: list[Any]
    reference: list[list[float]]
    scale: NDArray[np.float64]


@dataclass(frozen=True)
class System:
    """One benchmark system as coordinate arrays, with bw2calc's sign convention.

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
    ids: NDArray[np.int64] | None = None  # a real system: each product's process id in its archive

    @property
    def flow_offset(self) -> int:
        """Biosphere flow ids start here, so they never collide with product ids."""
        return self.profile.products

    def technosphere(self) -> sparse.csc_matrix:
        """The technosphere matrix bw2calc builds from this system."""
        n = self.profile.products
        signed = np.where(self.tech_flip, -self.tech_data, self.tech_data)
        return sparse.csc_matrix((signed, (self.tech_rows, self.tech_cols)), shape=(n, n))

    def condition_estimate(self) -> float:
        """Estimate of the technosphere matrix's 1-norm condition number, ``||A||_1 * ||A^-1||_1``.

        scipy's ``onenormest`` on the SuperLU inverse is a lower bound, nearly always exact. It
        draws from numpy's global generator, so a fixed seed makes it repeatable and the
        caller's state is put back.
        """
        a = self.technosphere()
        lu = sla.splu(a)
        n = a.shape[0]
        inverse = sla.LinearOperator((n, n), matvec=lu.solve, rmatvec=lambda x: lu.solve(x, trans="T"))  # ty: ignore[unknown-argument, missing-argument]
        state = np.random.get_state()  # noqa: NPY002 - scipy draws from the global generator
        try:
            np.random.seed(0)  # noqa: NPY002
            return float(abs(a).sum(axis=0).max() * sla.onenormest(inverse))
        finally:
            np.random.set_state(state)  # noqa: NPY002

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

    def bw2data(self, db: str = "synth", bio: str = "bio") -> tuple[dict, dict, list[list]]:
        """This system as the dicts ``bw2data.Database.write`` and ``Method.write`` take."""
        return as_bw2data(self, db=db, bio=bio)


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
