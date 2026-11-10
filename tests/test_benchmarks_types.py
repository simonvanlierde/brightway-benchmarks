"""The benchmark modules import Brightway, so no test runs them; ty still sees what they ask of ``System``."""

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FLAGS = ["--ignore", "unresolved-import", "--output-format", "concise"]


TY = shutil.which("ty")


@pytest.mark.skipif(TY is None, reason="ty is a development dependency")
def test_benchmarks_use_only_attributes_system_has():
    out = subprocess.run(
        [str(TY), "check", "--config", 'src.include=["benchmarks"]', *FLAGS],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    ).stdout
    bad = [line for line in out.splitlines() if "unresolved-attribute" in line and "type `System`" in line]
    assert not bad, "\n".join(bad)
