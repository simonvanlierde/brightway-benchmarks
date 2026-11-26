from pathlib import Path

import pytest

from bwbench import profiles, synth
from bwbench.profiles import PROFILES_DIR, profile


def test_new_measurements_in_the_calibration_file_keep_the_digest(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    p = profile("ecoinvent")
    assert p.target
    target = tmp_path / p.target
    target.write_bytes((PROFILES_DIR / p.target).read_bytes())
    monkeypatch.setattr(profiles, "PROFILES_DIR", tmp_path)
    before, version = p.digest(), synth.profile_version()
    target.write_text(target.read_text().replace('"stats": {', '"stats": {"new_statistic": 1, ', 1))
    assert p.digest() == before
    assert synth.profile_version() == version
    assert profile("ecoinvent", back=0.2).digest() != before  # a recalibration does change it


@pytest.mark.parametrize("field", ["products", "radius", "back", "units", "target"])
def test_every_profile_field_changes_the_digest(field: str):
    p = profile("ecoinvent")
    changed = {"products": 100, "radius": 0.5, "back": 0.3, "units": 1.0, "target": None}[field]
    assert profile("ecoinvent", **{field: changed}).digest() != p.digest()
