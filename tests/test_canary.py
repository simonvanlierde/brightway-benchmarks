"""scripts/canary.py: the nightly canary and its drift check."""

import importlib.util
import json
from pathlib import Path

import pytest

from bwbench.fingerprint import FIELDS, problems

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "canary.py"
spec = importlib.util.spec_from_file_location("canary", SCRIPT)
assert spec is not None
assert spec.loader is not None
canary = importlib.util.module_from_spec(spec)
spec.loader.exec_module(canary)

FP = dict.fromkeys(FIELDS) | {"version": 1, "kernel": "6.1"}


def test_run_writes_samples_medians_and_a_fingerprint(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(canary, "WORKLOADS", {"tiny": lambda: 7})
    monkeypatch.setenv("BWBENCH_COMMIT", "a" * 40)
    path = canary.run(tmp_path / "m")
    record = json.loads(path.read_text())
    assert path.parent == tmp_path / "m"
    assert len(record["samples"]["tiny"]) == canary.ROUNDS
    assert record["results"] == {"tiny": 7}
    assert record["commit"] == "a" * 40
    assert problems(record["fingerprint"]) == []


def test_the_workloads_are_hashed():
    """An edit to a workload starts a new history; this pins the shipped ones."""
    assert canary.workload_sha() == canary.workload_sha()
    assert set(canary.WORKLOADS) == {"interpreter", "memory"}


def night(folder: Path, day: int, seconds: float, *, sha: str = "s", fp: dict = FP) -> None:
    record = {"workload_sha256": sha, "median": {"interpreter": seconds}, "fingerprint": fp}
    folder.mkdir(exist_ok=True)
    (folder / f"202611{day:02d}T190500Z.json").write_text(json.dumps(record))


def test_too_little_history_moves_nothing(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    for day, s in enumerate([1.0, 1.0, 1.0, 1.0, 2.0], start=1):
        night(tmp_path, day, s)
    assert canary.check(tmp_path) == 0
    assert "too little history" in capsys.readouterr().out


@pytest.mark.parametrize(("latest", "code"), [(1.02, 0), (0.98, 0), (1.05, 1), (0.9, 1)])
def test_a_move_beyond_the_noise_fails(tmp_path: Path, latest: float, code: int):
    for day, s in enumerate([1.0, 1.01, 0.99, 1.0, 1.005, 0.995], start=1):
        night(tmp_path, day, s)
    night(tmp_path, 9, latest)
    assert canary.check(tmp_path) == code


def test_noisy_nights_widen_the_limit(tmp_path: Path):
    for day, s in enumerate([1.0, 1.1, 0.9, 1.1, 0.9, 1.0], start=1):
        night(tmp_path, day, s)
    night(tmp_path, 9, 1.2)  # 20% off, inside three median deviations of 10%
    assert canary.check(tmp_path) == 0


def test_other_workloads_and_fingerprint_changes(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    for day in range(1, 7):
        night(tmp_path, day, 2.0, sha="old")  # an earlier version of the workloads
    night(tmp_path, 8, 1.0)
    night(tmp_path, 9, 1.0, fp=FP | {"kernel": "6.2"})
    assert canary.check(tmp_path) == 0
    out = capsys.readouterr().out
    assert "against 1 earlier nights" in out
    assert "fingerprint kernel: 6.1 -> 6.2" in out


def test_usage_and_an_empty_folder(tmp_path: Path):
    assert canary.main(["check", str(tmp_path)]) == 2
    assert canary.main(["stir"]) == 2
