import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture
def box(tmp_path: Path) -> tuple[Path, Path]:
    """A copy of box.sh in a scratch repo, with a docker stub that logs its arguments."""
    (tmp_path / "scripts").mkdir()
    shutil.copy(REPO / "scripts" / "box.sh", tmp_path / "scripts")
    shutil.copytree(REPO / "docker", tmp_path / "docker")
    stub = tmp_path / "stub"
    stub.mkdir()
    log = tmp_path / "docker.log"
    # `docker image inspect` fails when STUB_NO_IMAGE is set, as if the image were missing.
    (stub / "docker").write_text(
        f'#!/bin/sh\nprintf "%s\\n" "$@" >> {log}\necho --- >> {log}\n[ "$1 ${{STUB_NO_IMAGE:-}}" != "image 1" ]\n'
    )
    (stub / "docker").chmod(0o755)
    return tmp_path, log


def run_box(repo: Path, **env: str) -> subprocess.CompletedProcess:
    path = f"{repo / 'stub'}:/usr/bin:/bin"
    return subprocess.run(
        ["/bin/bash", str(repo / "scripts" / "box.sh"), "echo", "hi"],
        env={"PATH": path, **env},
        capture_output=True,
        text=True,
        check=False,
    )


def test_box_runs_with_no_bwbench_variables(box: tuple[Path, Path]):
    repo, log = box
    out = run_box(repo)
    assert out.returncode == 0, out.stderr
    assert "run" in log.read_text().split("\n")


def test_box_passes_bwbench_variables(box: tuple[Path, Path]):
    repo, log = box
    assert run_box(repo, BWBENCH_SIZES="smoke").returncode == 0
    assert "BWBENCH_SIZES=smoke" in log.read_text().split("\n")


def test_box_mounts_the_repo_read_only_and_drops_privileges(box: tuple[Path, Path]):
    repo, log = box
    assert run_box(repo).returncode == 0
    args = log.read_text().split("\n")
    assert f"{repo}:/src:ro" in args
    writable = {a for a in args if a.startswith(str(repo)) and not a.endswith(":ro")}
    # asv/ holds the tracked configs and release lists, so it stays read-only too.
    assert writable == {f"{repo}/{d}:/src/{d}" for d in (".asv", "results", "site")}
    for flag in ("--init", "--cap-drop", "--security-opt", "--pids-limit"):
        assert flag in args


def test_box_rebuilds_the_image_when_the_dockerfile_changes(box: tuple[Path, Path]):
    repo, log = box

    def built_tag() -> str:
        log.write_text("")
        out = run_box(repo, STUB_NO_IMAGE="1")
        assert out.returncode == 0, out.stderr
        assert "building the box image" in out.stderr
        args = log.read_text().split("\n")
        return args[args.index("-t") + 1]

    first = built_tag()
    assert first.startswith("bwbench-box:")
    assert built_tag() == first
    with (repo / "docker" / "Dockerfile").open("a") as f:
        f.write("# edited\n")
    assert built_tag() != first


def test_box_labels_exit_137_as_out_of_memory(box: tuple[Path, Path]):
    repo, _ = box
    (repo / "stub" / "docker").write_text('#!/bin/sh\n[ "$1" = image ] && exit 0\nexit 137\n')
    out = run_box(repo)
    assert out.returncode == 137
    assert "OOM" in out.stderr


def test_box_stays_quiet_on_other_failures(box: tuple[Path, Path]):
    repo, _ = box
    (repo / "stub" / "docker").write_text('#!/bin/sh\n[ "$1" = image ] && exit 0\nexit 3\n')
    out = run_box(repo)
    assert out.returncode == 3
    assert "137" not in out.stderr
