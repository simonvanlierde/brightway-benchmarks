from pathlib import Path

import pytest

from bwbench.cache import data_root


def test_datapackages_follow_xdg_cache_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """The box gives every run a new home and keeps the cache under .asv/ with XDG_CACHE_HOME."""
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    assert data_root() == tmp_path / "bwbench"
    monkeypatch.delenv("XDG_CACHE_HOME")
    assert data_root() == Path.home() / ".cache" / "bwbench"
