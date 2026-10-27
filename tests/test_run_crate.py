"""scripts/run_crate.py on a fake results folder."""

import hashlib
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


def test_identical_files_of_two_subjects_keep_their_own_runs(tmp_path: Path):
    """machine.json is the same in every subject: each copy goes to the run that wrote it there."""
    spec = importlib.util.spec_from_file_location("run_crate", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    same = '{"machine": "m", "version": 1}'
    digest = hashlib.sha256(same.encode()).hexdigest()
    for subject, commit, when in (("bw2calc", "a" * 40, "20261027T010000Z"), ("bw2data", "b" * 40, "20261027T020000Z")):
        (tmp_path / subject / "m").mkdir(parents=True)
        (tmp_path / subject / "m" / "machine.json").write_text(same)
        # asv.sh lists the files as asv's results_dir names them, relative to the repo root.
        (tmp_path / subject / "m" / f"bwbench-run-{when}-{commit[:12]}.txt").write_text(
            f"commit {commit}\ngenerator 3\n{digest}  .asv/../results/{subject}/m/machine.json\n"
        )
    graph = {e["@id"]: e for e in module.crate(tmp_path)["@graph"]}
    assert "bw2calc/m/machine.json" in [r["@id"] for r in graph[f"#run-{'a' * 40}"]["result"]]
    assert "bw2data/m/machine.json" in [r["@id"] for r in graph[f"#run-{'b' * 40}"]["result"]]
