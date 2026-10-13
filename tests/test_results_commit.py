"""scripts/results-commit.sh in throwaway git repos, with a fixed host name."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "results-commit.sh"
GIT = shutil.which("git") or "git"
HOST = "benchhost7"  # what the hostname shim reports; long enough to count as a name


@pytest.fixture
def env(tmp_path: Path) -> dict[str, str]:
    if not shutil.which("rsync"):
        pytest.skip("needs rsync")
    shim = tmp_path / "bin"
    shim.mkdir()
    (shim / "hostname").write_text(f'#!/bin/sh\n[ "$1" = -f ] && echo {HOST}.example.org || echo {HOST}\n')
    (shim / "hostname").chmod(0o755)
    return os.environ | {
        "PATH": f"{shim}:{os.environ['PATH']}",
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@example.org",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@example.org",
    }


def git(repo: Path, env: dict[str, str], *args: str) -> str:
    return subprocess.run([GIT, "-C", str(repo), *args], check=True, capture_output=True, text=True, env=env).stdout


def commit_results(repo: Path, env: dict[str, str]) -> subprocess.CompletedProcess:
    return subprocess.run([str(SCRIPT)], cwd=repo, capture_output=True, text=True, check=False, env=env)


def write(repo: Path, name: str, text: str = "{}") -> None:
    path = repo / "results" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def files_on_branch(repo: Path, env: dict[str, str]) -> list[str]:
    return git(repo, env, "ls-tree", "-r", "--name-only", "refs/heads/results").split()


@pytest.fixture
def repo(tmp_path: Path, env: dict[str, str]) -> Path:
    repo = tmp_path / "a"
    repo.mkdir()
    git(repo, env, "init", "-q", "-b", "main")
    (repo / "README").write_text("x")
    git(repo, env, "add", "README")
    git(repo, env, "commit", "-q", "-m", "init")
    return repo


def test_first_run_starts_an_empty_branch_with_result_files_only(repo: Path, env: dict[str, str]):
    write(repo, "bw2calc/pinned-e0/abc-env.json")
    write(repo, "bw2calc/pinned-e0/evil.sh", "echo hi")
    (repo / "results" / "bw2calc" / "pinned-e0" / "link.json").symlink_to("/etc/hostname")
    assert commit_results(repo, env).returncode == 0
    assert files_on_branch(repo, env) == ["bw2calc/pinned-e0/abc-env.json"]
    assert git(repo, env, "log", "--format=%P", "-1", "refs/heads/results").strip() == ""  # its own history
    assert "nothing new" in commit_results(repo, env).stdout
    assert "results-branch" not in git(repo, env, "worktree", "list")


def test_updates_files_and_never_deletes_them(repo: Path, env: dict[str, str]):
    write(repo, "bw2calc/pinned-e0/a.json", '{"v": 1}')
    write(repo, "bw2calc/pinned-e0/b.json")
    assert commit_results(repo, env).returncode == 0
    write(repo, "bw2calc/pinned-e0/a.json", '{"v": 2}')
    (repo / "results" / "bw2calc" / "pinned-e0" / "b.json").unlink()
    assert commit_results(repo, env).returncode == 0
    assert files_on_branch(repo, env) == ["bw2calc/pinned-e0/a.json", "bw2calc/pinned-e0/b.json"]
    assert git(repo, env, "show", "refs/heads/results:bw2calc/pinned-e0/a.json") == '{"v": 2}'
    assert git(repo, env, "rev-list", "--count", "refs/heads/results").strip() == "2"


def test_a_commit_hook_does_not_stop_it(repo: Path, env: dict[str, str]):
    hook = repo / ".git" / "hooks" / "pre-commit"
    hook.write_text("#!/bin/sh\nexit 1\n")
    hook.chmod(0o755)
    write(repo, "bw2calc/pinned-e0/a.json")
    assert commit_results(repo, env).returncode == 0


def test_clones_share_one_history(repo: Path, env: dict[str, str], tmp_path: Path):
    write(repo, "bw2calc/pinned-e0/a.json")
    assert commit_results(repo, env).returncode == 0
    clone = tmp_path / "b"
    git(tmp_path, env, "clone", "-q", str(repo), str(clone))
    write(clone, "bw2calc/pinned-p0/b.json")
    assert commit_results(clone, env).returncode == 0  # builds on origin/results
    git(clone, env, "merge-base", "refs/heads/results", "refs/remotes/origin/results")
    git(clone, env, "push", "-q", "origin", "results")

    # The first clone's local branch is now behind origin: it moves forward first.
    git(repo, env, "fetch", "-q", str(clone), "results:refs/remotes/origin/results")
    write(repo, "bw2calc/pinned-e0/c.json")
    assert commit_results(repo, env).returncode == 0
    assert files_on_branch(repo, env) == [
        "bw2calc/pinned-e0/a.json",
        "bw2calc/pinned-e0/c.json",
        "bw2calc/pinned-p0/b.json",
    ]


def test_refuses_a_branch_that_diverged_from_origin(repo: Path, env: dict[str, str], tmp_path: Path):
    write(repo, "bw2calc/pinned-e0/a.json")
    assert commit_results(repo, env).returncode == 0
    clone = tmp_path / "b"
    git(tmp_path, env, "clone", "-q", str(repo), str(clone))
    write(clone, "bw2calc/pinned-p0/b.json")
    assert commit_results(clone, env).returncode == 0
    write(repo, "bw2calc/pinned-e0/d.json")
    assert commit_results(repo, env).returncode == 0  # origin moves on without the clone's commit
    git(clone, env, "fetch", "-q", "origin")
    run = commit_results(clone, env)
    assert run.returncode == 1
    assert "diverged" in run.stderr


@pytest.mark.parametrize(
    ("name", "text", "extra"),
    [
        ("bw2calc/m/machine.json", f'{{"machine": "{HOST}-e0"}}', {}),  # in the contents
        (f"bw2calc/{HOST.upper()}-e0/x.json", "{}", {}),  # in a folder name, any case
        ("bw2calc/m/machine.json", '{"machine": "lab-alias-1"}', {"BWBENCH_PRIVATE_NAMES": "lab-alias-1"}),
    ],
)
def test_refuses_results_that_name_this_host(repo: Path, env: dict[str, str], name: str, text: str, extra: dict):
    write(repo, name, text)
    run = commit_results(repo, env | extra)
    assert run.returncode == 1
    assert "name this host" in run.stderr
    assert "results" not in git(repo, env, "branch")


def test_files_it_does_not_publish_are_not_checked(repo: Path, env: dict[str, str]):
    write(repo, "bw2calc/m/a.json")
    write(repo, "bw2calc/m/run.log", f"ran on {HOST}")
    assert commit_results(repo, env).returncode == 0
    assert files_on_branch(repo, env) == ["bw2calc/m/a.json"]
