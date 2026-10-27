import json
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


def run_in_box(tmp_path: Path, command: str) -> tuple[int, str]:
    """in-box.sh with /src moved into a scratch folder, running a shell command: its pid and stdout."""
    script = tmp_path / "in-box.sh"
    script.write_text((REPO / "scripts" / "in-box.sh").read_text().replace("/src", str(tmp_path)))
    with subprocess.Popen(
        ["/bin/sh", str(script), "sh", "-c", command],
        env={"PATH": "/usr/bin:/bin", "HOME": str(tmp_path), "TMPDIR": str(tmp_path)},
        stdout=subprocess.PIPE,
        text=True,
    ) as proc:
        out, _ = proc.communicate()
    return proc.pid, out


def test_in_box_execs_the_command(tmp_path: Path):
    # The command must replace in-box.sh, so signals sent to the box reach it directly.
    pid, out = run_in_box(tmp_path, "echo $$")
    assert out.strip() == str(pid)


def test_in_box_config_does_not_outlive_the_run(tmp_path: Path):
    """A run that writes config to its home leaves nothing for the next; the caches stay in .asv/."""
    _, first = run_in_box(tmp_path, "mkdir -p $HOME/.config/pip && touch $HOME/.config/pip/pip.conf && echo $HOME")
    _, second = run_in_box(tmp_path, "echo $HOME; ls -A $HOME; echo $UV_NO_CONFIG $PIP_CONFIG_FILE")
    home, *rest = second.split()
    assert home != first.strip()
    assert rest == [".gitconfig", "1", "/dev/null"]  # only what in-box.sh itself writes
    _, caches = run_in_box(tmp_path, "echo $XDG_CACHE_HOME $UV_CACHE_DIR")
    assert caches.split() == [f"{tmp_path}/.asv/home/.cache", f"{tmp_path}/.asv/uv-cache"]


def test_box_lets_codspeed_turn_aslr_off_with_seccomp_on(box: tuple[Path, Path]):
    repo, log = box
    assert run_box(repo).returncode == 0
    assert not any(a.startswith("seccomp=") for a in log.read_text().split("\n"))
    log.write_text("")
    assert run_box(repo, BWBENCH_TARGET="codspeed").returncode == 0
    args = log.read_text().split("\n")
    assert f"seccomp={repo}/docker/seccomp-noaslr.json" in args
    assert not any("unconfined" in a for a in args)
    for flag in ("--cap-drop", "no-new-privileges"):
        assert flag in args


def test_box_refuses_codspeed_on_an_oss_bench_that_cannot_turn_aslr_off(box: tuple[Path, Path]):
    repo, _ = box
    stub = repo / "stub" / "oss-bench"
    stub.write_text("#!/bin/sh\n# knows OSS_BENCH_RW only\nexit 0\n")
    stub.chmod(0o755)
    out = run_box(repo, BWBENCH_TARGET="codspeed")
    assert out.returncode == 2
    assert "cannot turn ASLR off" in out.stderr


def test_seccomp_profile_is_dockers_default_plus_addr_no_randomize():
    profile = json.loads((REPO / "docker" / "seccomp-noaslr.json").read_text())
    assert profile["defaultAction"] == "SCMP_ACT_ERRNO"
    personality = [r for r in profile["syscalls"] if r["names"] == ["personality"]]
    allowed = {r["args"][0]["value"] for r in personality}
    assert 0x40000 in allowed  # ADDR_NO_RANDOMIZE; the rest are Docker's own, which moby may change
    assert all(r["action"] == "SCMP_ACT_ALLOW" and r["args"][0]["op"] == "SCMP_CMP_EQ" for r in personality)


def test_box_passes_the_commit_in(box: tuple[Path, Path]):
    """Git cannot read a worktree's .git from inside the box, so box.sh names the commit."""
    repo, log = box
    git = ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t.test", "-c", "commit.gpgsign=false"]
    subprocess.run([*git, "init", "-q"], check=True)
    subprocess.run([*git, "commit", "-q", "--allow-empty", "-m", "x"], check=True)
    head = subprocess.run([*git, "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    assert run_box(repo).returncode == 0
    assert f"BWBENCH_COMMIT={head}" in log.read_text().split("\n")
