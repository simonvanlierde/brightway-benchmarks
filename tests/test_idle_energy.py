"""Idle sampling handles repeated wraps without waiting five minutes in a test."""

import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "idle_energy.py"


def load():
    spec = importlib.util.spec_from_file_location("idle_energy", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_sums_multiple_wraps(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    module = load()
    (tmp_path / "max_energy_range_uj").write_text("100000000")
    counter = tmp_path / "energy_uj"
    counter.write_text("80000000")
    readings = iter(["20000000", "60000000", "0"])
    clock = iter([0, 5, 10, 15])
    monkeypatch.setattr(module.time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(module.time, "sleep", lambda _: counter.write_text(next(readings)))
    result = module.sample(tmp_path, seconds=15)
    assert result["joules"] == pytest.approx(120, rel=1e-12, abs=0)
    assert result["idle_w"] == pytest.approx(8, rel=1e-12, abs=0)


def test_rejects_sampling_gap(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    module = load()
    (tmp_path / "max_energy_range_uj").write_text("100000000")
    (tmp_path / "energy_uj").write_text("100")
    clock = iter([0, 61])
    monkeypatch.setattr(module.time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(module.time, "sleep", lambda _: None)
    with pytest.raises(RuntimeError, match="discard this baseline"):
        module.sample(tmp_path)
