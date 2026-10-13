"""scripts/results-commit.sh in throwaway git repos."""

import os
import shutil
import socket
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "results-commit.sh"
GIT_ENV = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.org",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.org",
}


GIT = shutil.which("git") or "git"


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        [GIT, "-C", str(repo), *args], check=True, capture_output=True, text=True, env=os.environ | GIT_ENV
    ).stdout


def commit_results(repo: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [str(SCRIPT)], cwd=repo, capture_output=True, text=True, check=False, env=os.environ | GIT_ENV
    )


def write(repo: Path, name: str, text: str = "{}") -> None:
    path = repo / "results" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    if not shutil.which("rsync"):
        pytest.skip("needs rsync")
    repo = tmp_path / "a"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    (repo / "README").write_text("x")
    git(repo, "add", "README")
    git(repo, "commit", "-q", "-m", "init")
    return repo


def test_first_run_starts_an_empty_branch_with_result_files_only(repo: Path):
    write(repo, "bw2calc/pinned-e0/abc-env.json")
    write(repo, "bw2calc/pinned-e0/evil.sh", "echo hi")
    assert commit_results(repo).returncode == 0
    assert git(repo, "ls-tree", "-r", "--name-only", "results").split() == ["bw2calc/pinned-e0/abc-env.json"]
    assert git(repo, "log", "--format=%P", "-1", "refs/heads/results").strip() == ""  # no parent: its own history
    assert "nothing new" in commit_results(repo).stdout
    assert ".asv/results-branch" not in git(repo, "worktree", "list")


def test_a_second_clone_builds_on_the_pushed_branch_and_keeps_other_machines(repo: Path, tmp_path: Path):
    write(repo, "bw2calc/pinned-e0/a.json")
    assert commit_results(repo).returncode == 0
    clone = tmp_path / "b"
    git(tmp_path, "clone", "-q", str(repo), str(clone))
    write(clone, "bw2calc/pinned-p0/b.json")
    assert commit_results(clone).returncode == 0
    files = git(clone, "ls-tree", "-r", "--name-only", "results").split()
    assert files == ["bw2calc/pinned-e0/a.json", "bw2calc/pinned-p0/b.json"]
    git(clone, "merge-base", "results", "origin/results")  # one history: a push fast-forwards


def test_refuses_results_that_name_this_host(repo: Path):
    write(repo, "bw2calc/pinned-e0/machine.json", f'{{"machine": "{socket.gethostname().split(".")[0]}-e0"}}')
    run = commit_results(repo)
    assert run.returncode == 1
    assert "name this host" in run.stderr
    assert "results" not in git(repo, "branch")
