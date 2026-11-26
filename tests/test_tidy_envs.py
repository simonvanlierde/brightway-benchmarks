"""scripts/tidy_envs.py: drop stale asv environments, hardlink identical files across the rest."""

import fcntl
import importlib.util
import os
import time
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "tidy_envs.py"
spec = importlib.util.spec_from_file_location("tidy_envs", SCRIPT)
assert spec is not None
assert spec.loader is not None
tidy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tidy)

BIG = tidy.MIN_SIZE


def env(root: Path, name: str, files: dict[str, bytes], age_days: float = 0) -> Path:
    e = root / name
    for rel, data in files.items():
        (e / rel).parent.mkdir(parents=True, exist_ok=True)
        (e / rel).write_bytes(data)
    then = time.time() - age_days * 86400
    for p in [e, *e.rglob("*")]:
        os.utime(p, (then, then))
    return e


def test_prunes_only_environments_unused_for_days(tmp_path: Path):
    old = env(tmp_path, "bw2calc/old", {"lib/a.py": b"x"}, age_days=40)
    new = env(tmp_path, "bw2calc/new", {"lib/a.py": b"x"}, age_days=40)
    (new / "lib" / "b.py").write_bytes(b"a commit installed today")
    assert tidy.prune([tmp_path / "bw2calc"], 30, time.time()) == [old]
    assert not old.exists()
    assert new.exists()


def test_links_identical_files_and_keeps_the_rest(tmp_path: Path):
    same = b"n" * BIG
    a = env(tmp_path, "s/a", {"numpy.so": same, "own.so": b"a" * BIG, "small.py": b"tiny"})
    b = env(tmp_path, "s/b", {"numpy.so": same, "own.so": b"b" * BIG, "small.py": b"tiny"})
    assert tidy.link_duplicates([tmp_path / "s"]) == BIG
    assert (a / "numpy.so").stat().st_ino == (b / "numpy.so").stat().st_ino
    assert (b / "numpy.so").read_bytes() == same
    assert (a / "own.so").stat().st_ino != (b / "own.so").stat().st_ino
    assert (a / "small.py").stat().st_ino != (b / "small.py").stat().st_ino  # below MIN_SIZE
    assert not list(tmp_path.rglob("*.tidy-link"))
    assert tidy.link_duplicates([tmp_path / "s"]) == 0  # a second run has nothing left to do


def test_files_with_another_mode_stay_apart(tmp_path: Path):
    a = env(tmp_path, "s/a", {"bin/tool": b"t" * BIG})
    b = env(tmp_path, "s/b", {"bin/tool": b"t" * BIG})
    (a / "bin" / "tool").chmod(0o755)
    assert tidy.link_duplicates([tmp_path / "s"]) == 0
    assert (b / "bin" / "tool").stat().st_ino != (a / "bin" / "tool").stat().st_ino


def test_an_inode_already_shared_frees_nothing(tmp_path: Path):
    # subjects are walked in the order given, so a's copy is kept and b's is replaced
    a = env(tmp_path, "s1/a", {"x.so": b"x" * BIG})
    b = env(tmp_path, "s2/b", {"x.so": b"x" * BIG})
    (tmp_path / "cache").mkdir()
    os.link(b / "x.so", tmp_path / "cache" / "x.so")  # as uv's cache holds what it installed
    assert tidy.link_duplicates([tmp_path / "s1", tmp_path / "s2"]) == 0  # the cache keeps b's inode
    assert (a / "x.so").stat().st_ino == (b / "x.so").stat().st_ino


def test_a_failed_link_keeps_the_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    a = env(tmp_path, "s/a", {"numpy.so": b"n" * BIG})
    b = env(tmp_path, "s/b", {"numpy.so": b"n" * BIG})

    def refuse(*_: object) -> None:
        raise OSError(18, "Invalid cross-device link")

    monkeypatch.setattr(tidy.os, "link", refuse)
    assert tidy.link_duplicates([tmp_path / "s"]) == 0
    assert (b / "numpy.so").read_bytes() == b"n" * BIG
    assert (a / "numpy.so").stat().st_ino != (b / "numpy.so").stat().st_ino
    assert not list(tmp_path.rglob("*" + tidy.TMP))


def test_main_skips_a_subject_asv_holds_and_sweeps_leftovers(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    envs = tmp_path / "env"
    env(envs, "busy/old", {"a": b"x"}, age_days=40)
    env(envs, "s/old", {"a": b"x"}, age_days=40)
    left = env(envs, "s/new", {"numpy.so" + tidy.TMP: b"half done"}) / ("numpy.so" + tidy.TMP)
    with (tmp_path / "busy.lock").open("w") as held:
        fcntl.flock(held, fcntl.LOCK_EX)  # what scripts/asv.sh holds during a run
        assert tidy.main([str(envs), "--dry-run"]) == 0
        out = capsys.readouterr().out
        assert out.startswith("would remove 1 environments unused for 30 days")
        assert left.exists()
        assert tidy.main([str(envs)]) == 0
    out = capsys.readouterr().out
    assert "  removed s/old" in out
    assert "  skipped busy: asv holds its lock" in out
    assert (envs / "busy" / "old").exists()
    assert not left.exists()
    with pytest.raises(SystemExit) as e:
        tidy.main([str(tmp_path / "missing")])
    assert e.value.code == 2
