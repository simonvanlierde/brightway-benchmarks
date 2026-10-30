"""USEEIO 1.1 as a ``System``: the real case beside the synthetic profiles.

USEEIO 1.1 is the US EPA's environmentally-extended input-output model (public domain, a
US government work): 388 commodities, 1,871 flows. Brightway's file server hosts it as the
project archive that ``bw2io.install_project("USEEIO-1.1")`` downloads. The archive carries the
processed bw_processing datapackages, so reading them needs no bw2io or bw2data.

``system`` renumbers the archive's database ids to 0 to n - 1 for products and n onwards
for flows, as the synthetic systems are, so every case that asks for ``{0: 1}`` or
``method_name(i)`` runs on it unchanged. Only the numbering changes, not a value.
"""

from __future__ import annotations

import hashlib
import tarfile
import tempfile
import urllib.request
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from numpy.typing import NDArray

    from bwbench.synth import Profile, System

# shortcut: pinned by hand. Move to sourceledger `format = "file"` once sourceledger 0.4.0 exists.
URL = "https://files.brightway.dev/USEEIO-1.1.tar.gz"
SHA256 = "3b9a21fc435d9218749370731affbe073dc42d1e0af02d3db80df3b2c8b5a335"
METHODS = ("GCC", "ACID", "ETOX")  # impact categories, by the archive's code: 41, 9 and 1,180 factors


def sha256_of(path: Path) -> str:
    """Hex SHA-256 of a file."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


def fetch(dest: Path, url: str = URL, sha256: str = SHA256) -> Path:
    """The archive at ``dest``, downloaded on first use. Raises if its SHA-256 is not ``sha256``.

    The download goes to a temporary name and is renamed only once it matches, so a stopped or
    corrupted download never leaves a file that passes for the archive.
    """
    if dest.exists() and sha256_of(dest) == sha256:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=dest.parent, prefix=dest.name, suffix=".part", delete=False) as tmp:
        part = Path(tmp.name)
    try:
        with urllib.request.urlopen(url, timeout=60) as response, part.open("wb") as out:  # noqa: S310 - a pinned https URL
            while chunk := response.read(1 << 20):
                out.write(chunk)
        if (got := sha256_of(part)) != sha256:
            msg = f"{url}: SHA-256 {got}, pinned {sha256}"
            raise ValueError(msg)
        part.replace(dest)
    finally:
        part.unlink(missing_ok=True)
    return dest


def remap(
    tech_indices: NDArray,
    tech_data: NDArray,
    tech_flip: NDArray,
    bio_indices: NDArray,
    bio_data: NDArray,
    cfs: list[tuple[NDArray, NDArray]],
) -> tuple[dict[str, NDArray], list[NDArray], list[NDArray]]:
    """Renumber database ids as ``System`` has them: products 0 to n - 1, flows n onwards.

    ``tech_indices`` and ``bio_indices`` have ``row`` and ``col`` fields; ``cfs`` holds one
    ``(flow ids, factors)`` per method. A column is a process, a row its product, and the
    production exchanges (``flip`` false) say which product belongs to which process: product
    ``i`` becomes the one of the ``i``-th process by id, so the production amounts sit on the
    diagonal. Factors for flows no process emits are dropped, as bw2calc drops them.
    Returns the system's arrays and the per-method flow ids and factors.
    """
    produced = ~tech_flip
    by_product = np.argsort(tech_indices["row"][produced])
    products = tech_indices["row"][produced][by_product]
    makers = tech_indices["col"][produced][by_product]  # makers[i] is the process of products[i]
    processes = np.sort(makers)
    n = processes.size
    if np.unique(products).size != n or np.unique(processes).size != n:
        msg = "a process makes two products, or a product has two processes"
        raise ValueError(msg)

    def product_index(ids: NDArray) -> NDArray[np.int64]:
        """The index of the process that makes each product id in ``ids``."""
        at = np.minimum(np.searchsorted(products, ids), n - 1)
        if not np.array_equal(products[at], ids):
            msg = "an exchange names a product no process makes"
            raise ValueError(msg)
        return np.searchsorted(processes, makers[at])

    flows = np.unique(bio_indices["row"])
    flow_index = lambda ids: np.searchsorted(flows, ids) + n  # noqa: E731
    arrays = {
        "tech_rows": product_index(tech_indices["row"]).astype(np.int64),
        "tech_cols": np.searchsorted(processes, tech_indices["col"]).astype(np.int64),
        "tech_data": tech_data.astype(np.float64),
        "tech_flip": tech_flip.astype(np.bool_),
        "bio_rows": flow_index(bio_indices["row"]).astype(np.int64),
        "bio_cols": np.searchsorted(processes, bio_indices["col"]).astype(np.int64),
        "bio_data": bio_data.astype(np.float64),
    }
    kept = [np.isin(ids, flows) for ids, _ in cfs]
    cf_flows = [flow_index(ids[k]).astype(np.int64) for (ids, _), k in zip(cfs, kept, strict=True)]
    cf_data = [factors[k].astype(np.float64) for (_, factors), k in zip(cfs, kept, strict=True)]
    return arrays, cf_flows, cf_data


def read(archive: Path) -> tuple[tuple, tuple, list[tuple[NDArray, NDArray]]]:
    """The technosphere, biosphere and ``METHODS`` characterization arrays of the archive's datapackages."""
    import bw_processing as bwp  # noqa: PLC0415 - only the container has it
    import fsspec  # noqa: PLC0415  # ty: ignore[unresolved-import] - a bw_processing dependency

    def column(dp: object, suffix: str) -> NDArray:
        name = next(r["name"] for r in dp.resources if r["name"].endswith(suffix))  # ty: ignore[unresolved-attribute]
        return dp.get_resource(name)[0]  # ty: ignore[unresolved-attribute]

    with tempfile.TemporaryDirectory() as tmp, tarfile.open(archive) as tar:
        members = [m for m in tar.getmembers() if m.isfile() and "/processed/" in m.name and m.name.endswith(".zip")]
        tar.extractall(tmp, members=members, filter="data")
        dps = [bwp.load_datapackage(fsspec.filesystem("zip", fo=str(z))) for z in sorted(Path(tmp).rglob("*.zip"))]
        # Resources load lazily from the zip, so read every array before the folder goes.
        database = next(dp for dp in dps if any(r["name"].endswith("_technosphere_matrix.flip") for r in dp.resources))
        tech = tuple(np.array(column(database, f"_technosphere_matrix.{k}")) for k in ("indices", "data", "flip"))
        bio = tuple(np.array(column(database, f"_biosphere_matrix.{k}")) for k in ("indices", "data"))
        cfs = []
        for code in METHODS:
            dp = next(
                dp for dp in dps if any(r["name"] == f"Impact_Potential_{code}_matrix_data.data" for r in dp.resources)
            )
            cfs.append(
                (
                    np.array(column(dp, f"Impact_Potential_{code}_matrix_data.indices")["row"]),
                    np.array(column(dp, f"Impact_Potential_{code}_matrix_data.data")),
                )
            )
    return tech, bio, cfs


def system(p: Profile, seed: int) -> System:
    """The USEEIO 1.1 system of profile ``p``, fetched into the cache on first use."""
    from bwbench.synth import System, data_root  # noqa: PLC0415 - synth imports this module

    tech, bio, cfs = read(fetch(data_root() / "useeio-1.1.tar.gz"))
    arrays, cf_flows, cf_data = remap(tech[0], tech[1], tech[2], bio[0], bio[1], cfs)
    n = int(arrays["tech_rows"].max()) + 1
    flows = int(arrays["bio_rows"].max()) + 1 - n
    if (n, flows, len(METHODS)) != (p.products, p.flows, p.methods):
        msg = f"the archive has {n} products and {flows} flows; the profile says {p.products} and {p.flows}"
        raise ValueError(msg)
    scale = np.ones(n)
    for a in (*arrays.values(), *cf_flows, *cf_data, scale):
        a.setflags(write=False)
    return System(
        "useeio",
        p,
        seed,
        arrays["tech_rows"],
        arrays["tech_cols"],
        arrays["tech_data"],
        arrays["tech_flip"],
        arrays["bio_rows"],
        arrays["bio_cols"],
        arrays["bio_data"],
        cf_flows,
        cf_data,
        scale,
    )
