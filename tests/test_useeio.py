import hashlib
import json
import sys
import zipfile
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from scipy import sparse

from bwbench import synth, useeio

IDX = [("row", "<i4"), ("col", "<i4")]


def indices(*pairs: tuple[int, int]) -> np.ndarray:
    return np.array(list(pairs), dtype=IDX)


def tiny() -> tuple:
    """Two processes (ids 50, 7) making products 90, 30; process 7 buys 0.25 of product 90 in two exchanges."""
    tech = indices((30, 7), (90, 50), (90, 7), (90, 7))
    data = np.array([2.0, 1.0, 0.1, 0.15])
    flip = np.array([False, False, True, True])
    bio = indices((700, 50), (500, 7))
    cfs = [(np.array([500, 700, 999]), np.array([3.0, 5.0, 9.0]))]  # flow 999 is emitted by no process
    return tech, data, flip, bio, np.array([4.0, 6.0]), cfs


def test_remap_numbers_products_and_flows_from_zero():
    tech, data, flip, bio, bio_data, cfs = tiny()
    a, cf_flows, cf_data = useeio.remap(tech, data, flip, bio, bio_data, cfs)
    # Process 7 is index 0 and makes product 30; process 50 is index 1 and makes product 90.
    assert a["tech_rows"].tolist() == [0, 1, 1, 1]
    assert a["tech_cols"].tolist() == [0, 1, 0, 0]
    assert a["bio_rows"].tolist() == [2 + 1, 2 + 0]  # flows 500 and 700 become 2 and 3
    assert a["bio_cols"].tolist() == [1, 0]
    assert cf_flows[0].tolist() == [2, 3]
    assert cf_data[0].tolist() == [3.0, 5.0]


def test_remap_keeps_the_solution():
    tech, data, flip, bio, bio_data, cfs = tiny()
    a, *_ = useeio.remap(tech, data, flip, bio, bio_data, cfs)
    got = sparse.csc_matrix(
        (np.where(a["tech_flip"], -a["tech_data"], a["tech_data"]), (a["tech_rows"], a["tech_cols"])), shape=(2, 2)
    )
    # A[product, process], products 30, 90 by processes 7, 50, with the duplicate cell summed.
    assert got.toarray().tolist() == [[2.0, 0.0], [-0.25, 1.0]]


def test_remap_refuses_an_exchange_for_a_product_nobody_makes():
    tech, data, flip, bio, bio_data, cfs = tiny()
    tech["row"][2] = 12
    with pytest.raises(ValueError, match="no process makes"):
        useeio.remap(tech, data, flip, bio, bio_data, cfs)


def test_remap_refuses_a_process_with_two_products():
    tech, data, flip, bio, bio_data, cfs = tiny()
    tech["col"][1] = 7
    with pytest.raises(ValueError, match="two products"):
        useeio.remap(tech, data, flip, bio, bio_data, cfs)


def test_fetch_downloads_once_and_checks_the_hash(tmp_path: Path):
    src = tmp_path / "src.bin"
    src.write_bytes(b"archive")
    good = hashlib.sha256(b"archive").hexdigest()
    dest = tmp_path / "cache" / "a.tar.gz"
    assert useeio.fetch(dest, src.as_uri(), good) == dest
    src.unlink()  # a hit never goes to the network
    assert useeio.fetch(dest, src.as_uri(), good) == dest

    bad = tmp_path / "cache" / "b.tar.gz"
    other = tmp_path / "other.bin"
    other.write_bytes(b"changed upstream")
    with pytest.raises(ValueError, match="SHA-256"):
        useeio.fetch(bad, other.as_uri(), good)
    assert not bad.exists()
    assert not list(bad.parent.glob("*.part"))


def test_fetch_replaces_a_file_that_does_not_match(tmp_path: Path):
    src = tmp_path / "src.bin"
    src.write_bytes(b"archive")
    dest = tmp_path / "a.tar.gz"
    dest.write_bytes(b"half a down")
    useeio.fetch(dest, src.as_uri(), hashlib.sha256(b"archive").hexdigest())
    assert dest.read_bytes() == b"archive"


def test_the_profile_stays_out_of_the_asv_version(monkeypatch: pytest.MonkeyPatch):
    base = synth.profile_version()
    monkeypatch.delitem(synth.PROFILES, "useeio")
    assert synth.profile_version() == base


def test_useeio_has_no_monte_carlo():
    with pytest.raises(NotImplementedError, match="uncertainty"):
        synth.system("useeio", uncertain=True)


class FixtureDatapackage:
    """Read the fixture's named NumPy resources using the loader's two-method contract."""

    def __init__(self, path: Path):
        self.path = path
        with zipfile.ZipFile(path) as archive:
            self.resources = json.loads(archive.read("datapackage.json"))["resources"]

    def get_resource(self, name: str) -> tuple[np.ndarray, dict]:
        resource = next(r for r in self.resources if r["name"] == name)
        with zipfile.ZipFile(self.path) as archive, archive.open(resource["path"]) as stream:
            return np.load(stream, allow_pickle=False), resource


@pytest.mark.parametrize("loader", ["fixture", "bw_processing"])
def test_archive_becomes_a_system_with_the_same_scores(loader: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    if loader == "bw_processing":
        pytest.importorskip("bw_processing", reason="real loader contract runs in the benchmark container")
    else:
        monkeypatch.setitem(sys.modules, "bw_processing", SimpleNamespace(load_datapackage=FixtureDatapackage))
        monkeypatch.setitem(sys.modules, "fsspec", SimpleNamespace(filesystem=lambda _protocol, *, fo: Path(fo)))
    archive = Path(__file__).parent / "fixtures" / "useeio-tiny.tar.gz"
    monkeypatch.setattr(useeio, "fetch", lambda _dest: archive)
    monkeypatch.setattr(synth, "data_root", lambda: tmp_path)
    result = useeio.system(synth.profile("useeio", products=3, flows=2), seed=0)

    # Product ids 30, 60, 120 belong to processes 7, 50, 90; flow 999 has no emissions.
    a = np.array([[2.0, 0.0, -0.5], [-0.25, 1.0, 0.0], [0.0, -0.125, 1.0]])
    b = np.array([[3.0, 0.0, 4.0], [0.0, 2.0, 0.0]])
    factors = np.array([[1.0, 2.0], [3.0, 4.0], [5.0, 6.0]])
    np.testing.assert_array_equal(result.technosphere().toarray(), a)
    np.testing.assert_array_equal(result.biosphere().toarray(), b)
    np.testing.assert_array_equal(result.cf_data, factors)
    np.testing.assert_array_equal(result.cf_flows, [[3, 4]] * 3)
    expected = (factors @ b @ np.linalg.solve(a, np.eye(3))).T
    np.testing.assert_allclose(result.reference, expected, rtol=1e-12)
    for array in (result.tech_data, result.bio_data, *result.cf_data):
        assert memoryview(array).readonly
