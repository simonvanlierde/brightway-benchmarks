"""benchmarks/bench_bw_timex/bench_timex.py and the bw2data helpers in bwbench, with fake Brightway packages."""

import importlib.util
import itertools
import os
import subprocess
import sys
import tempfile
import types
from pathlib import Path

import pytest

import bwbench

SCRIPT = Path(__file__).resolve().parents[1] / "benchmarks" / "bench_bw_timex" / "bench_timex.py"


def fake_bw2data(log: list[str]) -> types.ModuleType:
    """bw2data as the suite uses it: each write gives the database a new ``modified`` stamp."""
    bd = types.ModuleType("bw2data")
    stamp = itertools.count()
    databases: dict[str, dict[str, str]] = {}

    class Database:
        def __init__(self, name: str) -> None:
            self.name = name

        def write(self, _data: object) -> None:
            log.append(f"write {self.name}")
            databases[self.name] = {"modified": str(next(stamp))}

    class Method:
        def __init__(self, _name: object) -> None:
            pass

        def write(self, _data: object) -> None:
            pass

    vars(bd).update(
        Database=Database,
        Method=Method,
        databases=databases,
        projects=types.SimpleNamespace(set_current=lambda _name: None),
    )
    return bd


@pytest.fixture
def timex(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[types.ModuleType, list[str]]:
    """bench_timex loaded against fakes; the list logs background writes and bw_timex cache clears."""
    log: list[str] = []
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    monkeypatch.setenv("BRIGHTWAY2_DIR", "")  # the import sets it; monkeypatch puts it back
    timex = types.ModuleType("bw_timex")
    vars(timex).update(TimexLCA=object, clear_background_lci_cache=lambda: log.append("clear"))
    temporalis = types.ModuleType("bw_temporalis")
    vars(temporalis).update(TemporalDistribution=object)
    for name, fake in [
        ("bw2calc", types.ModuleType("bw2calc")),
        ("bw2data", fake_bw2data(log)),
        ("bw_timex", timex),
        ("bw_temporalis", temporalis),
    ]:
        monkeypatch.setitem(sys.modules, name, fake)
    spec = importlib.util.spec_from_file_location("bench_timex", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, "bench_timex", module)
    spec.loader.exec_module(module)
    synthetic = types.SimpleNamespace(bw2data=lambda db=None: ({}, {}, [{}]))  # noqa: ARG005
    monkeypatch.setattr(module, "system", lambda _size: synthetic)
    return module, log


def test_every_sample_starts_from_empty_bw_timex_caches(timex: tuple[types.ModuleType, list[str]]):
    """The backgrounds are written once per process, but bw_timex's caches are cleared before every sample."""
    module, log = timex
    for _ in range(3):
        module.build_background("smoke")
    assert log.count("write bg_2020") == 1
    assert log.count("clear") == 3
    assert log[-1] == "clear"  # after the writes, so no sample sees a solve cached before them


def test_a_rewritten_background_fails_the_stamp_check(timex: tuple[types.ModuleType, list[str]]):
    module, _ = timex
    before = module.build_background("smoke")
    assert set(before) == {"bio", "bg_2020", "bg_2030"}
    bwbench.assert_stamps_unchanged(before)
    sys.modules["bw2data"].Database("bg_2030").write({})
    with pytest.raises(AssertionError, match="rewrote the stored background"):
        bwbench.assert_stamps_unchanged(before)


def test_a_killed_process_leaves_no_brightway_dir_for_the_next(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """A process asv kills skips its atexit removal; the next one removes the dir of a pid no longer running."""
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    monkeypatch.setenv("BRIGHTWAY2_DIR", "")
    gone = subprocess.run([sys.executable, "-c", "import os; print(os.getpid())"], capture_output=True, check=True)
    dead = tmp_path / f"bwbench-{int(gone.stdout)}-x"
    (dead / "heating-timex").mkdir(parents=True)
    alive = tmp_path / f"bwbench-{os.getppid()}-x"
    alive.mkdir()
    other = tmp_path / "bwbench-x"  # not one of ours: no pid in its name
    other.mkdir()
    path = Path(bwbench.temporary_brightway_dir())
    assert path.name.startswith(f"bwbench-{os.getpid()}-")
    assert os.environ["BRIGHTWAY2_DIR"] == str(path)
    assert not dead.exists()
    assert alive.exists()
    assert other.exists()
