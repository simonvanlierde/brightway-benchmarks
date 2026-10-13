"""scripts/run_crate.py on a fake results folder."""

import importlib.util
import json
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "run_crate.py"


def test_crate_lists_every_file_and_the_profiles(tmp_path: Path):
    spec = importlib.util.spec_from_file_location("run_crate", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for name in ("abc123-env.json", "machine.json", "pylock.env.toml"):
        (tmp_path / name).write_text("{}")
    module.main.__globals__["sys"].argv = ["run_crate.py", str(tmp_path)]
    module.main()
    module.main()  # a rerun replaces the crate and does not list it as a part
    graph = {e["@id"]: e for e in json.loads((tmp_path / "ro-crate-metadata.json").read_text())["@graph"]}
    parts = [p["@id"] for p in graph["./"]["hasPart"]]
    assert parts == ["abc123-env.json", "machine.json", "pylock.env.toml"]
    assert graph["pylock.env.toml"]["description"].startswith("PEP 751")
    assert graph["#profile-ecoinvent"]["value"]
    assert graph["#run"]["instrument"]["@id"].startswith("https://github.com/simonvanlierde/brightway-benchmarks")
