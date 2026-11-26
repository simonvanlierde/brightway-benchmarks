"""scripts/tidy_envs.py: drop asv environments unused for days, hardlink identical files across the rest."""

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
DAY = 86400


def env(root: Path, name: str, files: dict[str, bytes], used_days_ago: float = 0) -> Path:
    """An environment whose install status asv last touched `used_days_ago` days ago."""
    e = root / name
    for rel, data in {"asv-install-status.json": b"{}", **files}.items():
        (e / rel).parent.mkdir(parents=True, exist_ok=True)
        (e / rel).write_bytes(data)
    then = time.time() - used_days_ago * DAY
    os.utime(e / "asv-install-status.json", (then, then))
    return e


def test_prunes_only_environments_asv_has_not_used(tmp_path: Path):
    old = env(tmp_path, "bw2calc/old", {"lib/a.py": b"x"}, used_days_ago=40)
    rerun = env(tmp_path, "bw2calc/rerun", {"lib/a.py": b"x"}, used_days_ago=40)
    # a rerun of an installed commit only reads the status file: its access time moves, not its mtime
    os.utime(rerun / "asv-install-status.json", (time.time(), time.time() - 40 * DAY))
    assert tidy.prune([tmp_path / "bw2calc"], 30, time.time()) == [old]
    assert not old.exists()
    assert rerun.exists()
    assert not list(tmp_path.rglob("*" + tidy.GONE))


def test_a_failed_delete_leaves_no_environment_under_its_name(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    old = env(tmp_path, "s/old", {"lib/a.py": b"x"}, used_days_ago=40)
    monkeypatch.setattr(tidy.shutil, "rmtree", lambda *_, **__: None)  # say a read-only folder stops it
    assert tidy.prune([tmp_path / "s"], 30, time.time()) == [old]
    assert not old.exists()  # asv would rebuild it rather than reuse half an environment
    assert (tmp_path / "s" / ("old" + tidy.GONE)).exists()  # the next run finishes the delete


def test_a_stopped_delete_is_finished_and_never_counted(tmp_path: Path):
    half = env(tmp_path, "s/abc" + tidy.GONE, {"lib/a.py": b"x"}, used_days_ago=40)
    assert tidy.prune([tmp_path / "s"], 30, time.time()) == []
    assert not half.exists()


def test_links_identical_files_and_keeps_the_rest(tmp_path: Path):
    same = b"n" * BIG
    a = env(tmp_path, "s/a", {"numpy.so": same, "own.so": b"a" * BIG, "small.py": b"tiny"})
    b = env(tmp_path, "s/b", {"numpy.so": same, "own.so": b"b" * BIG, "small.py": b"tiny"})
    assert tidy.link_duplicates([tmp_path / "s"], dry_run=True) == BIG
    assert (a / "numpy.so").stat().st_ino != (b / "numpy.so").stat().st_ino  # a dry run links nothing
    assert tidy.link_duplicates([tmp_path / "s"]) == BIG
    assert (a / "numpy.so").stat().st_ino == (b / "numpy.so").stat().st_ino
    assert (b / "numpy.so").read_bytes() == same
    assert (a / "own.so").stat().st_ino != (b / "own.so").stat().st_ino
    assert (a / "small.py").stat().st_ino != (b / "small.py").stat().st_ino  # below MIN_SIZE
    assert not list(tmp_path.rglob("*" + tidy.TMP))
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


def test_a_failed_rename_keeps_the_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    a = env(tmp_path, "s/a", {"numpy.so": b"n" * BIG})
    b = env(tmp_path, "s/b", {"numpy.so": b"n" * BIG})

    def refuse(*_: object) -> None:
        raise OSError(16, "Device or resource busy")

    monkeypatch.setattr(tidy.Path, "replace", refuse)  # the link is made, the swap fails
    assert tidy.link_duplicates([tmp_path / "s"]) == 0
    assert (b / "numpy.so").read_bytes() == b"n" * BIG
    assert (a / "numpy.so").stat().st_ino != (b / "numpy.so").stat().st_ino
    assert not list(tmp_path.rglob("*" + tidy.TMP))


def test_a_symlinked_environment_is_left_alone(tmp_path: Path):
    outside = env(tmp_path, "outside/e", {"a": b"x"}, used_days_ago=40)
    (tmp_path / "env" / "s").mkdir(parents=True)
    (tmp_path / "env" / "s" / "link").symlink_to(outside)
    assert tidy.prune([tmp_path / "env" / "s"], 30, time.time()) == []
    assert outside.exists()


def test_main_holds_the_locks_and_skips_a_subject_asv_holds(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
):
    envs = tmp_path / "env"
    env(envs, "busy/old", {}, used_days_ago=40)
    env(envs, "s/old", {}, used_days_ago=40)
    left = env(envs, "s/new", {"numpy.so" + tidy.TMP: b"half done"}) / ("numpy.so" + tidy.TMP)
    prune = tidy.prune

    def prune_while_asv_tries(*args: object, **kwargs: object) -> list[Path]:
        with (tmp_path / "s.lock").open("w") as asv, pytest.raises(BlockingIOError):
            fcntl.flock(asv, fcntl.LOCK_EX | fcntl.LOCK_NB)  # what scripts/asv.sh does
        return prune(*args, **kwargs)

    monkeypatch.setattr(tidy, "prune", prune_while_asv_tries)
    with (tmp_path / "busy.lock").open("w") as held:
        fcntl.flock(held, fcntl.LOCK_EX)
        assert tidy.main([str(envs), "--dry-run"]) == 0
        out = capsys.readouterr().out
        assert out.startswith("would remove 1 environments unused for 30 days")
        assert (envs / "s" / "old").exists()
        assert left.exists()
        assert tidy.main([str(envs), "--days", "50"]) == 0
        assert capsys.readouterr().out.startswith("removed 0 environments unused for 50 days")
        assert tidy.main([str(envs)]) == 0
    out = capsys.readouterr().out
    assert "  removed s/old" in out
    assert "  skipped busy: asv holds its lock" in out
    assert (envs / "busy" / "old").exists()
    assert not left.exists()


@pytest.mark.parametrize("argv", [["missing"], [".", "--days", "0"]])
def test_main_usage_errors(tmp_path: Path, argv: list[str]):
    with pytest.raises(SystemExit) as e:
        tidy.main([str(tmp_path / argv[0]), *argv[1:]])
    assert e.value.code == 2
