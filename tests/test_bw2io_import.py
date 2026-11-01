"""Sampled imports keep readable links to either relative or absolute releases."""

import importlib.util
from pathlib import Path

import pytest


@pytest.mark.parametrize("relative", [True, False])
def test_subset_links_resolve_to_the_release(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, relative: bool
) -> None:
    script = Path(__file__).resolve().parents[1] / "scripts" / "bw2io_import.py"
    spec = importlib.util.spec_from_file_location("bw2io_import", script)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    release = tmp_path / "release"
    (release / "datasets").mkdir(parents=True)
    (release / "MasterData").mkdir()
    (release / "datasets" / "one.spold").write_text("dataset")
    (release / "MasterData" / "flows.xml").write_text("flows")
    monkeypatch.chdir(tmp_path)
    source = Path("release") if relative else release
    sample = module.subset(source, "1", tmp_path / "sample")
    assert (sample / "datasets" / "one.spold").read_text() == "dataset"
    assert (sample / "MasterData" / "flows.xml").read_text() == "flows"
