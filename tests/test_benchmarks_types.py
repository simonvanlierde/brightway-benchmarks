"""The benchmark modules import Brightway, so no test runs them; ty still sees what they ask of ``System``."""

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FLAGS = ["--ignore", "import-not-found", "--output-format", "concise", "--exit-zero"]


TY = shutil.which("ty")


@pytest.mark.skipif(TY is None, reason="ty is a development dependency")
def test_benchmarks_use_only_attributes_system_has():
    run = subprocess.run(
        [str(TY), "check", "--config", 'src.include=["benchmarks"]', *FLAGS],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert run.returncode == 0, run.stdout + run.stderr
    bad = [line for line in run.stdout.splitlines() if "missing-attribute" in line and "type `System`" in line]
    assert not bad, "\n".join(bad)
