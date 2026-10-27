"""scripts/compat.sh with uv stubbed out: what it resolves, records and runs."""

import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]

# Logs each call with the cutoff and config it saw. `uv venv` makes a python that logs and exits
# with $FAKE_PYTEST_EXIT, at Scripts/python.exe if $FAKE_WINDOWS is set (a Windows venv);
# `uv pip compile -o FILE` appends its stdin to $LOG.in and writes $LOCK to FILE.
UV = """#!/bin/sh
echo "$* cutoff=${UV_EXCLUDE_NEWER-unset} config=${UV_NO_CONFIG-on}" >>"$LOG"
case "$1 $2" in
"pip compile")
    { echo "--- $*"; cat; } >>"$LOG.in"
    while [ $# -gt 0 ]; do [ "$1" = -o ] && printf '%s\\n' "${LOCK:-lock}" >"$2"; shift; done
    ;;
venv*)
    for a; do venv=$a; done
    py=$venv/bin/python
    [ -z "${FAKE_WINDOWS-}" ] || py=$venv/Scripts/python.exe
    mkdir -p "$(dirname "$py")"
    echo '#!/bin/sh' >"$py"
    echo 'echo "python $* PYTHONPATH=$PYTHONPATH strict=$BWBENCH_STRICT solver=${BWBENCH_SOLVER-unset}" >>"$LOG"' \
        >>"$py"
    echo 'exit ${FAKE_PYTEST_EXIT:-0}' >>"$py"
    chmod +x "$py"
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


def compat(repo: Path, *args: str, **env: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["/bin/sh", "scripts/compat.sh", "3.13", *args],
        cwd=repo,
        env={
            "PATH": f"{repo / 'stub'}:/usr/bin:/bin",
            "TMPDIR": str(repo),
            "LOG": str(repo / "log"),
            # in-box.sh's cutoff, which this column must not inherit.
            "UV_EXCLUDE_NEWER": "2026-10-06T00:00:00Z",
            # A knob from the calling shell, which would make pytest import pyklu.
            "BWBENCH_SOLVER": "klu",
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
    # No config: pyproject.toml's week-long exclude-newer must not hold releases back either.
    assert all("cutoff=unset config=1" in line for line in log if not line.startswith("python"))
    assert log[-1].startswith("python -m pytest")
    assert "benchmarks/codspeed" in log[-1]
    assert log[-1].endswith("PYTHONPATH=benchmarks strict=1 solver=unset")


def test_an_empty_strict_lets_platform_gaps_skip(repo: Path):
    # The macOS and Windows jobs set it empty: a solver their wheels lack is not a release problem.
    out = compat(repo, BWBENCH_STRICT="")
    assert out.returncode == 0, out.stderr
    assert (repo / "log").read_text().splitlines()[-1].endswith("strict= solver=unset")


def test_a_failing_set_is_still_recorded(repo: Path):
    out = compat(repo, FAKE_PYTEST_EXIT="1")
    assert out.returncode == 1
    assert (repo / ".asv" / "compat" / "3.13-latest" / "requirements.txt").read_text() == "lock\n"


def compiles(repo: Path) -> list[str]:
    """Each `uv pip compile` call: its arguments, then the requirements it read."""
    return (repo / "log.in").read_text().split("--- ")[1:]


def test_floors_lowers_only_what_brightway_depends_on(repo: Path):
    # The latest set, as `--annotation-style line` writes it.
    lock = """\
bw2data==4.5             # via bw2io
bw-processing==1.1       # via bw2calc
matrix-utils==0.6
ecoinvent-interface==3.1 # via brightway25
numpy==2.3.4             # via bw2calc, pandas
pandas==3.1.0            # via bw2io
loguru==0.7.3            # via ipython, bw-timex
six==1.17.0              # via python-dateutil
pluggy==1.6.0            # via pytest
pytest==9.0.1"""
    out = compat(repo, "floors", LOCK=lock)
    assert out.returncode == 0, out.stderr
    floors = repo / ".asv" / "compat" / "3.13-floors"
    assert (floors / "requirements.txt").exists()
    assert (floors / "latest.txt").exists()
    first, second = compiles(repo)
    assert "--annotation-style line" in first
    args, *reqs = second.splitlines()
    assert "--resolution lowest-direct" in args
    assert "--no-build" in args
    # Brightway and the test harness pinned at latest, Brightway's own dependencies unpinned
    # (lowest-direct takes them to their floor), and the rest left to the resolver.
    pinned = {"bw2data==4.5", "bw-processing==1.1", "matrix-utils==0.6", "ecoinvent-interface==3.1", "pytest==9.0.1"}
    assert pinned | {"numpy", "pandas", "loguru"} <= set(reqs)
    assert not {"numpy==2.3.4", "six", "six==1.17.0", "pluggy", "pluggy==1.6.0"} & set(reqs)


def test_pre_allows_pre_releases(repo: Path):
    out = compat(repo, "pre")
    assert out.returncode == 0, out.stderr
    (only,) = compiles(repo)
    assert "--prerelease allow" in only
    assert (repo / ".asv" / "compat" / "3.13-pre" / "requirements.txt").exists()


def test_an_unknown_column_stops_before_resolving(repo: Path):
    out = compat(repo, "newest")
    assert out.returncode == 2
    assert "latest|floors|pre" in out.stderr
    assert not (repo / "log").exists()


def test_a_windows_venv_runs_its_scripts_python(repo: Path):
    out = compat(repo, FAKE_WINDOWS="1")
    assert out.returncode == 0, out.stderr
    log = (repo / "log").read_text()
    assert "Scripts/python.exe" in log
    assert log.splitlines()[-1].startswith("python -m pytest")
