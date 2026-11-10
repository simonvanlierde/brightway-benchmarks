"""scripts/dataset.py: what may ship, and its checksums."""

import hashlib
import importlib
import uuid
from pathlib import Path
from types import ModuleType

import pytest

from bwbench import ecospold
from bwbench.synth import system

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


@pytest.fixture
def dataset(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    monkeypatch.syspath_prepend(str(SCRIPTS))
    return importlib.import_module("dataset")


def test_archive_profiles_are_refused(dataset: ModuleType):
    left_out = dataset.refused(["smoke", "bafu", "useeio", "nope"])
    assert set(left_out) == {"bafu", "useeio", "nope"}
    assert "BAFU-2025-v2" in left_out["bafu"]


def test_ecospold_files_with_synthetic_flows_are_clean_and_real_ids_are_caught(dataset: ModuleType, tmp_path: Path):
    s = system("smoke")
    ecospold.write_ecospold(s, tmp_path / "ok", dataset.flow_ids(s.profile))
    assert all(not dataset.licensed_hits(f.read_bytes()) for f in (tmp_path / "ok" / "datasets").iterdir())
    random_ids = [str(uuid.UUID(int=j + 1, version=4)) for j in range(s.profile.flows + 5)]  # as a real biosphere's
    ecospold.write_ecospold(s, tmp_path / "real", random_ids)
    files = list((tmp_path / "real" / "datasets").iterdir())
    assert all(dataset.licensed_hits(f.read_bytes()) for f in files)
    with pytest.raises(ValueError, match="UUID"):
        dataset.zip_folder(tmp_path / "real", tmp_path / "real.zip", scan=True)
    assert dataset.licensed_hits(b'<a xmlns="http://www.EcoInvent.org/EcoSpold02">ecoinvent 3.12</a>')


def test_manifest_matches_sha256sum(dataset: ModuleType, tmp_path: Path):
    (tmp_path / "a.zip").write_bytes(b"one")
    (tmp_path / "README.md").write_text("two")
    files = dataset.write_manifest(tmp_path)
    assert [f["path"] for f in files] == ["README.md", "a.zip"]
    assert files[1]["sha256"] == hashlib.sha256(b"one").hexdigest()
    sums = (tmp_path / "SHA256SUMS").read_text()
    assert sums == f"{hashlib.sha256(b'two').hexdigest()} *README.md\n{hashlib.sha256(b'one').hexdigest()} *a.zip\n"
    dataset.write_manifest(tmp_path)  # a rerun does not list SHA256SUMS itself
    assert "SHA256SUMS" not in (tmp_path / "SHA256SUMS").read_text()


def test_zenodo_limits_are_enforced(dataset: ModuleType):
    dataset.check_zenodo([{"bytes": 1}] * 99)
    with pytest.raises(ValueError, match="Zenodo"):
        dataset.check_zenodo([{"bytes": 1}] * 100)
    with pytest.raises(ValueError, match="Zenodo"):
        dataset.check_zenodo([{"bytes": 51 * 10**9}])
