"""scripts/compat.sh with uv stubbed out: what it resolves, records and runs."""

import shutil
import subprocess
import tarfile
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

# Logs each call; `pixi lock` writes pixi.lock next to the manifest, and `pixi install` makes the
# environment's python, which logs its arguments and prints a package for `-c`.
PIXI = """#!/bin/sh
echo "pixi $*" >>"$LOG"
for a; do manifest=$a; done
env=$(dirname "$manifest")
case $1 in
lock) echo "lock for $(sed -n 's/^python = //p' "$manifest")" >"$env/pixi.lock" ;;
install)
    mkdir -p "$env/.pixi/envs/default/bin"
    py=$env/.pixi/envs/default/bin/python
    echo '#!/bin/sh' >"$py"
    echo '[ "$1" = -c ] && { echo bw2calc==3.1.0; exit; }' >>"$py"
    echo 'echo "python $* PYTHONPATH=$PYTHONPATH strict=$BWBENCH_STRICT" >>"$LOG"' >>"$py"
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
    (tmp_path / "stub" / "pixi").write_text(PIXI)
    (tmp_path / "stub" / "pixi").chmod(0o755)
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
            "UV_EXCLUDE_NEWER": "2026-10-20T00:00:00Z",
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


def test_locks_the_resolved_set_as_pylock_toml(repo: Path):
    out = compat(repo, LOCK="numpy==2.5.4")
    assert out.returncode == 0, out.stderr
    assert (repo / ".asv" / "compat" / "3.13-latest" / "pylock.toml").exists()
    _, lock = compiles(repo)
    assert "pylock.toml" in lock.splitlines()[0]
    assert lock.splitlines()[1:] == ["numpy==2.5.4"]  # read from requirements.txt, not resolved again


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
    first, second, _lock = compiles(repo)
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
    only, _lock = compiles(repo)
    assert "--prerelease allow" in only
    assert (repo / ".asv" / "compat" / "3.13-pre" / "requirements.txt").exists()


def test_conda_forge_installs_with_pixi_and_leaves_out_what_it_lacks(repo: Path):
    out = compat(repo, "conda-forge")
    assert out.returncode == 0, out.stderr
    log = (repo / "log").read_text().splitlines()
    assert not [line for line in log if not line.startswith(("pixi ", "python "))]  # no uv
    assert log[0].startswith("pixi lock")
    assert "--frozen" in log[1]
    # The set is on record before the cases run: the manifest, its lock and the Python packages.
    cell = repo / ".asv" / "compat" / "3.13-conda-forge"
    assert 'python = "3.13.*"' in (cell / "pixi.toml").read_text()
    assert (cell / "pixi.lock").read_text() == 'lock for "3.13.*"\n'
    assert (cell / "requirements.txt").read_text() == "bw2calc==3.1.0\n"
    run = log[-1]
    assert run.startswith("python -m pytest")
    assert run.endswith("PYTHONPATH=benchmarks strict=1")
    assert "--ignore=benchmarks/codspeed/test_bw_graph_tools.py --ignore=benchmarks/codspeed/test_bw_timex.py" in run
    assert "bw_timex is not on conda-forge" in out.stderr


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


def test_suites_installs_the_test_needs_and_runs_the_package_suites(repo: Path):
    (repo / "scripts" / "compat-suites.sh").write_text('echo "suites $*" >>"$LOG"\n')
    out = compat(repo, "suites")
    assert out.returncode == 0, out.stderr
    only, _lock = compiles(repo)
    assert {"brightway25", "bw_timex", "pytest-mock", "bw_temporalis"} <= set(only.splitlines()[1:])
    log = (repo / "log").read_text().splitlines()
    assert log[-1].endswith("/bin/python .asv/compat/3.13-suites")  # the suites, not the benchmarks
    assert not any(line.startswith("python") for line in log)


# Serves $FAKE/REPO-TAG.tar.gz for a tag's archive URL, else fails like curl -f on a 404.
CURL = """#!/bin/sh
for a; do case $a in -o) next=1 ;; *) [ -z "${next-}" ] || { dest=$a; next=; }; url=$a ;; esac; done
repo=${url#https://github.com/brightway-lca/}; repo=${repo%%/*}
src=$FAKE/$repo-${url##*/}
[ -e "$src" ] && cp "$src" "$dest" || exit 22
"""

# Runs as the env's python from inside the package's folder: logs what it saw, and fails the
# suite of the package named in $FAKE/fail.
PYTHON = """#!/bin/sh
[ "$1" != -c ] || exec python3 "$@"
here=$(basename "$PWD")
echo "$here $* files=$(ls | tr '\\n' ' ')ini=$(tr '\\n' ';' <pytest.ini)" >>"$LOG"
[ "$here" = "$(cat "$FAKE/fail" 2>/dev/null)" ] || exit 0
echo "FAILED tests/test_e2e.py::test_alpha - TypeError: nested"
echo "ERROR tests/test_io.py::test_beta"
exit 1
"""


# A package's pytest settings: compat-suites.sh keeps only testpaths.
PYPROJECT = """[tool.pytest.ini_options]
addopts = "--cov"
testpaths = ["tests/*.py", "tests/sub/*.py"]
"""


def suites(tmp_path: Path, tags: list[str], deselect: str = "", fail: str = "") -> tuple[int, Path]:
    """Run compat-suites.sh on REQUIREMENTS, with GitHub serving TAGS (REPO-TAG) and FAIL's suite failing."""
    fake = tmp_path / "fake"
    fake.mkdir()
    (fake / "fail").write_text(fail)
    for name, body in (("curl", CURL), ("python", PYTHON)):
        (fake / name).write_text(body)
        (fake / name).chmod(0o755)
    for repo_tag in tags:
        src = tmp_path / "src" / f"{repo_tag}" / "tests"
        src.mkdir(parents=True)
        (src / "test_it.py").write_text("")
        (src.parent / "pyproject.toml").write_text(PYPROJECT)
        (src.parent / "src").mkdir()  # a source tree, which must not shadow the installed package
        with tarfile.open(fake / f"{repo_tag}.tar.gz", "w:gz") as tar:
            tar.add(src.parent, arcname=repo_tag)
    out = tmp_path / ".asv" / "compat" / "3.12-suites"
    out.mkdir(parents=True)
    (out / "requirements.txt").write_text(REQUIREMENTS)
    script = (REPO / "scripts" / "compat-suites.sh").read_text()
    if deselect:
        script = script.replace("<<'EOF'\nEOF", f"<<'EOF'\n{deselect}\nEOF")
    (tmp_path / "compat-suites.sh").write_text(script)
    rc = subprocess.run(
        ["/bin/sh", "compat-suites.sh", fake / "python", ".asv/compat/3.12-suites"],
        cwd=tmp_path,
        env={"PATH": f"{fake}:/usr/bin:/bin", "FAKE": str(fake), "LOG": str(tmp_path / "log")},
        capture_output=True,
        text=True,
        check=False,
    ).returncode
    return rc, out


REQUIREMENTS = """\
bw2data==4.8
bw2calc==3.1.0
bw2io==0.9.17
bw-processing==1.6
matrix-utils==0.9
bw-graph-tools==0.10
bw-timex==1.4.1
numpy==2.5.4
"""


def test_suites_reports_each_package_and_the_failing_tests(tmp_path: Path):
    tags = [
        "brightway2-data-4.8",
        "brightway2-calc-3.1.0",
        # brightway2-io has no tag for its version
        "bw_processing-1.6",
        "matrix_utils-0.9",
        "bw_graph_tools-0.10",
        "bw_timex-v1.4.1",  # bw_timex tags with a v
    ]
    deselect = "bw-timex tests/test_e2e.py::test_x[a-b]  # needs the network"
    rc, out = suites(tmp_path, tags, deselect=deselect, fail="bw-timex")
    assert rc == 1
    assert (out / "suites.txt").read_text() == (
        "bw2data 4.8 passed\n"
        "bw2calc 3.1.0 passed\n"
        "bw2io 0.9.17 no tag\n"
        "bw-processing 1.6 passed\n"
        "matrix-utils 0.9 passed\n"
        "bw-graph-tools 0.10 passed\n"
        "bw-timex 1.4.1 failed\n"
        "    FAILED tests/test_e2e.py::test_alpha\n"
        "    ERROR tests/test_io.py::test_beta\n"
    )
    log = (tmp_path / "log").read_text().splitlines()
    # Only tests/ and pyproject.toml are unpacked, and of its pytest settings only testpaths applies.
    ini = "ini=[pytest];testpaths = tests/*.py tests/sub/*.py;"
    assert log[0] == f"bw2data -m pytest -p no:cacheprovider -rfE files=pyproject.toml pytest.ini tests {ini}"
    assert log[-1].startswith("bw-timex -m pytest -p no:cacheprovider -rfE --deselect tests/test_e2e.py::test_x[a-b] ")
    assert (out / "suites" / "bw-timex.log").exists()
    assert not (out / "suites" / "bw-timex").exists()  # the unpacked tests go once they ran


def test_suites_pass_when_every_package_passes(tmp_path: Path):
    tags = ["brightway2-data-4.8", "brightway2-calc-3.1.0", "brightway2-io-0.9.17", "bw_processing-1.6"]
    tags += ["matrix_utils-0.9", "bw_graph_tools-0.10", "bw_timex-v1.4.1"]
    rc, out = suites(tmp_path, tags)
    assert rc == 0
    assert (out / "suites.txt").read_text().count(" passed\n") == 7
