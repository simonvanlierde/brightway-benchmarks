"""scripts/run_crate.py on a fake results folder."""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "run_crate.py"


def test_crate_lists_every_file_and_the_profiles(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    spec = importlib.util.spec_from_file_location("run_crate", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    (tmp_path / "bw2calc" / "m1").mkdir(parents=True)
    names = (
        "bw2calc/benchmarks.json",
        "bw2calc/m1/abc123-env.json",
        "bw2calc/m1/machine.json",
        "bw2calc/m1/pylock.env.toml",
    )
    for name in names:
        (tmp_path / name).write_text("{}")
    monkeypatch.setattr(sys, "argv", ["run_crate.py", str(tmp_path)])
    module.main()
    module.main()  # a rerun replaces the crate and does not list it as a part
    graph = {e["@id"]: e for e in json.loads((tmp_path / "ro-crate-metadata.json").read_text())["@graph"]}
    parts = [p["@id"] for p in graph["./"]["hasPart"]]
    assert parts == list(names)
    assert graph["bw2calc/m1/pylock.env.toml"]["description"].startswith("PEP 751")
    assert graph["bw2calc/m1/machine.json"]["description"] == "asv machine description"
    assert "m1" not in graph["./"]["name"]  # machine folders carry host names; the dataset name must not
    assert graph["#profile-ecoinvent"]["value"]
    # No bwbench-run record lists them, so the commit that wrote them is unknown.
    assert graph["#run-unknown"]["instrument"]["@id"] == "https://github.com/simonvanlierde/brightway-benchmarks"
