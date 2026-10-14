import json
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_smoke.py"


def run(root: Path) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, SCRIPT, root], capture_output=True, text=True, check=False)


def write(root: Path, results: dict) -> None:
    folder = root / "bw2calc" / "smoke"
    folder.mkdir(parents=True)
    (folder / "machine.json").write_text("{}")
    (folder / "abc-uv-py3.12.json").write_text(json.dumps({"results": results}))


def test_passes_skipped_and_finished_results(tmp_path: Path):
    write(tmp_path, {"a.time": [[0.1, float("nan")]], "b.track": [1e-16]})
    assert run(tmp_path).returncode == 0


def test_fails_on_a_null_result(tmp_path: Path):
    write(tmp_path, {"a.time": [[0.1, None]], "b.time": [None]})
    out = run(tmp_path)
    assert out.returncode == 1
    assert "a.time" in out.stdout
    assert "b.time" in out.stdout


def test_fails_when_nothing_ran(tmp_path: Path):
    assert run(tmp_path).returncode == 1


def test_fails_on_an_empty_results_object(tmp_path: Path):
    write(tmp_path, {})
    out = run(tmp_path)
    assert out.returncode == 1
    assert "abc-uv-py3.12.json" in out.stdout


def test_fails_when_a_subject_has_no_result_file(tmp_path: Path):
    write(tmp_path, {"a.time": [[0.1]]})
    (tmp_path / "bw2data" / "smoke").mkdir(parents=True)
    out = run(tmp_path)
    assert out.returncode == 1
    assert "bw2data" in out.stdout
    assert "bw2calc" not in out.stdout
