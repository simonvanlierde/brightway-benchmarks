"""scripts/profile.sh: the arguments become the install and the profile call, with uv and the venv script stubbed."""

import re
import shutil
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def profile(tmp_path: Path, *args: str) -> tuple[subprocess.CompletedProcess, list[str]]:
    scripts = tmp_path / "scripts"
    scripts.mkdir(exist_ok=True)
    shutil.copy(REPO / "scripts" / "profile.sh", scripts)
    log = tmp_path / "log"
    # Both stubs record their argument list, one line per call.
    # The script wipes its venv first, so the venv stub makes the interpreter stub ($1 is the venv).
    (scripts / "codspeed-venv.sh").write_text(
        f'#!/bin/sh\necho "venv $*" >>{log}\nmkdir -p "$1/bin"\n'
        f'printf \'#!/bin/sh\\necho "py $BWBENCH_PROFILE_WITH|$*" >>{log}\\n\' >"$1/bin/python"\n'
        'chmod +x "$1/bin/python"\n'
    )
    stub = tmp_path / "stub"
    stub.mkdir(exist_ok=True)
    (stub / "uv").write_text(f'#!/bin/sh\necho "uv $*" >>{log}\n')
    (stub / "uv").chmod(0o755)
    run = subprocess.run(
        ["/bin/sh", "scripts/profile.sh", *args],
        cwd=tmp_path,
        env={"PATH": f"{stub}:/usr/bin:/bin"},
        capture_output=True,
        text=True,
        check=False,
    )
    return run, log.read_text().splitlines() if log.exists() else []


def test_arguments_become_the_environment_and_the_parameters(tmp_path: Path):
    run, log = profile(tmp_path, "bw2calc", "lci", "release=2.1.0", "with=pypardiso", "with=scikit-umfpack", "n=5")
    assert run.returncode == 0, run.stderr
    assert log[0].endswith("bw2calc bw2calc==2.1.0 pypardiso scikit-umfpack")
    assert log[-1] == "py  pypardiso scikit-umfpack|-m bwbench.profiling bw2calc lci n=5"


def test_without_options_the_latest_is_installed_with_no_packages(tmp_path: Path):
    run, log = profile(tmp_path, "bw2calc", "lci")
    assert run.returncode == 0, run.stderr
    assert log[0].endswith("bw2calc")
    assert log[-1] == "py |-m bwbench.profiling bw2calc lci"


def test_a_bad_argument_exits_2_before_installing(tmp_path: Path):
    run, log = profile(tmp_path, "bw2calc", "lci", "junk")
    assert run.returncode == 2
    assert "junk is not release=X" in run.stderr
    assert log == []


def test_the_pyinstrument_pin_is_the_one_in_pyproject(tmp_path: Path):
    _, log = profile(tmp_path, "bw2calc", "lci")
    pin = re.search(r'"(pyinstrument==[^"]+)"', (REPO / "pyproject.toml").read_text())
    assert pin
    assert log[1].endswith(pin.group(1))
