"""`just site` reads the `ratios` branch: a missing branch is fine, a failed fetch is not."""

import os
import shutil
import subprocess
import textwrap
from pathlib import Path

GIT = shutil.which("git") or "git"
REPOSITORY = Path(__file__).resolve().parents[1]
ENV = {
    "PATH": os.defpath,
    "HOME": "/nonexistent",
    "LANG": "C.UTF-8",
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_CONFIG_GLOBAL": "/dev/null",
}


def git(*args: str, cwd: Path) -> None:
    subprocess.run([GIT, *args], cwd=cwd, env=ENV, check=True, capture_output=True)


def fetch_ratios(tmp_path: Path, origin: str) -> subprocess.CompletedProcess[str]:
    """The `site` recipe's ratios lines, run in a checkout whose origin is ORIGIN."""
    recipe = (REPOSITORY / "justfile").read_text(encoding="utf-8")
    start = recipe.index("    rm -rf build/ratios")
    end = recipe.index("    fi\n", recipe.index("no ratios branch yet", start)) + len("    fi\n")
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    git("init", "-q", cwd=checkout)
    git("remote", "add", "origin", origin, cwd=checkout)
    return subprocess.run(
        ["/bin/bash", "-euo", "pipefail", "-c", textwrap.dedent(recipe[start:end])],
        cwd=checkout,
        env=ENV,
        capture_output=True,
        text=True,
        check=False,
    )


def origin(tmp_path: Path, *, ratios: bool) -> Path:
    work = tmp_path / "work"
    work.mkdir()
    git("init", "-q", "-b", "ratios" if ratios else "main", cwd=work)
    (work / "hosted").mkdir()
    (work / "hosted/Linux.json").write_text("{}", encoding="utf-8")
    git("add", ".", cwd=work)
    git(
        "-c",
        "user.name=Ada",
        "-c",
        "user.email=ada@example.org",
        "-c",
        "commit.gpgsign=false",
        "commit",
        "-q",
        "-m",
        "ratios",
        cwd=work,
    )
    return work


def test_the_ratios_branch_lands_in_build_ratios(tmp_path: Path):
    result = fetch_ratios(tmp_path, str(origin(tmp_path, ratios=True)))
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "checkout/build/ratios/hosted/Linux.json").exists()


def test_no_ratios_branch_builds_without_comparisons(tmp_path: Path):
    result = fetch_ratios(tmp_path, str(origin(tmp_path, ratios=False)))
    assert result.returncode == 0, result.stderr
    assert "no ratios branch yet" in result.stderr


def test_a_failed_fetch_fails_the_build(tmp_path: Path):
    result = fetch_ratios(tmp_path, str(tmp_path / "unreachable"))
    assert result.returncode != 0
    assert "no ratios branch yet" not in result.stderr
