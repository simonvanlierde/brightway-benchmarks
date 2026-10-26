"""scripts/compat.sh with uv stubbed out: what it resolves, records and runs."""

import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]

# Logs each call with the cutoff it saw. `uv venv` makes a python that logs and exits with
# $FAKE_PYTEST_EXIT; `uv pip compile -o FILE` writes FILE; `uv pip freeze` prints one line.
UV = """#!/bin/sh
echo "$* cutoff=${UV_EXCLUDE_NEWER-unset}" >>"$LOG"
case "$1 $2" in
"pip compile") while [ $# -gt 0 ]; do [ "$1" = -o ] && echo lock >"$2"; shift; done ;;
"pip freeze") echo "bw2calc==9.9" ;;
venv*)
    for a; do venv=$a; done
    mkdir -p "$venv/bin"
    echo '#!/bin/sh' >"$venv/bin/python"
    echo 'echo "python $* PYTHONPATH=$PYTHONPATH" >>"$LOG"; exit ${FAKE_PYTEST_EXIT:-0}' >>"$venv/bin/python"
    chmod +x "$venv/bin/python"
    ;;
esac
"""


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    (tmp_path / "scripts").mkdir()
    shutil.copy(REPO / "scripts" / "compat.sh", tmp_path / "scripts")
    (tmp_path / "stub").mkdir()
    (tmp_path / "stub" / "uv").write_text(UV)
    (tmp_path / "stub" / "uv").chmod(0o755)
    return tmp_path


def compat(repo: Path, **env: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["/bin/sh", "scripts/compat.sh", "3.13"],
        cwd=repo,
        env={
            "PATH": f"{repo / 'stub'}:/usr/bin:/bin",
            "TMPDIR": str(repo),
            "LOG": str(repo / "log"),
            # in-box.sh's cutoff, which this column must not inherit.
            "UV_EXCLUDE_NEWER": "2026-10-06T00:00:00Z",
            **env,
        },
        capture_output=True,
        text=True,
        check=False,
    )


def test_resolves_the_newest_releases_and_runs_every_suite(repo: Path):
    out = compat(repo)
    assert out.returncode == 0, out.stderr
    log = (repo / "log").read_text().splitlines()
    assert all("cutoff=unset" in line for line in log if not line.startswith("python"))
    # --no-config: pyproject.toml's week-long exclude-newer must not hold releases back either.
    assert all("--no-config" in line for line in log if not line.startswith("python"))
    assert any(line.startswith("pip compile") and "--python-version 3.13" in line for line in log)
    assert log[-1].startswith("python -m pytest")
    assert "benchmarks/codspeed" in log[-1]
    assert log[-1].endswith("PYTHONPATH=benchmarks")


def test_a_failing_set_is_still_recorded(repo: Path):
    out = compat(repo, FAKE_PYTEST_EXIT="1")
    assert out.returncode == 1
    assert (repo / ".asv" / "compat" / "3.13" / "pylock.toml").read_text() == "lock\n"
    assert (repo / ".asv" / "compat" / "3.13" / "freeze.txt").read_text() == "bw2calc==9.9\n"
