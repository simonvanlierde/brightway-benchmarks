"""scripts/release_report.py: counting one asv result file."""

import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "release_report.py"


def load():
    spec = importlib.util.spec_from_file_location("release_report", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_tally_counts_ok_failed_and_skipped():
    result = {
        "commit_hash": "0123456789abcdef",
        "env_name": "env-a",
        "results": {
            "bench_lca.A.time_x": [[1.0, None, float("nan")]],
            "bench_lca.B.time_y": [None],
            "bench_lca.C.time_z": [0.5],
        },
    }
    assert load().tally(json.dumps(result)) == ("01234567", "env-a", 2, 2, 1, ["A.time_x", "B.time_y"])


@pytest.mark.parametrize(
    "text", ["", "{", "[]", '{"results": {"a.b": []}}', '{"results": {"nodot": [null]}}', "[" * 100_000]
)
def test_tally_rejects_malformed_input(text: str):
    with pytest.raises((ValueError, RecursionError, AttributeError, IndexError, KeyError, TypeError)):
        load().tally(text)


def test_main_orders_releases_and_fails_on_a_missing_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    module = load()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(module, "sha", lambda _mirror, tag: f"{tag:0<8}"[:8])  # no asv mirror here
    (tmp_path / "asv").mkdir()
    (tmp_path / "asv" / "s.hashes").write_text("1.0\n2.0\n")
    folder = tmp_path / ".asv" / "stack" / "s" / "m"
    folder.mkdir(parents=True)
    (folder / "machine.json").write_text("{}")
    (folder / "x-env.json").write_text(json.dumps({"commit_hash": "2.000000", "env_name": "e", "results": {}}))
    assert module.main("s") == 1
    rows = capsys.readouterr().out.splitlines()[2:]
    assert rows == ["| 2.0 | e | 0 | 0 | 0 |  |", "| 1.0 | missing | | | | no result file |"]

    (folder / "y-env.json").write_text(json.dumps({"commit_hash": "1.000000", "env_name": "e", "results": {}}))
    assert module.main("s") == 0
    assert [r.split(" |")[0] for r in capsys.readouterr().out.splitlines()[2:]] == ["| 1.0", "| 2.0"]
