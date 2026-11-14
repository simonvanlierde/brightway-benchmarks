"""src/bwbench/fingerprint.py: the environment fingerprint every result carries."""

import json
import subprocess
import sys
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from bwbench import fingerprint as fpmod
from bwbench.fingerprint import FIELDS, fingerprint, problems

SCRIPT = Path(fpmod.__file__)


def test_this_machine_has_a_valid_fingerprint(tmp_path: Path):
    lock = tmp_path / "pylock.toml"
    lock.write_text("lock-version = '1.0'\n")
    fp = fingerprint(lock)
    assert list(fp) == list(FIELDS)
    assert problems(fp) == []
    assert problems(json.loads(json.dumps(fp))) == []
    assert fp["lock"]["name"] == "pylock.toml"
    assert fp["python"].endswith(".".join(map(str, sys.version_info[:3])))


def test_any_python_can_run_the_file_on_its_own(tmp_path: Path):
    """Asv's environments run it by path, with -I: nothing beside it may be imported."""
    lock = tmp_path / "versions.txt"
    lock.write_text("numpy==2.5.3\n")
    out = subprocess.run([sys.executable, "-I", str(SCRIPT), str(lock)], capture_output=True, text=True, check=True)
    fp = json.loads(out.stdout)
    assert problems(fp) == []
    assert fp["lock"]["sha256"] == fingerprint(lock)["lock"]["sha256"]
    bad = subprocess.run([sys.executable, "-I", str(SCRIPT), "--json"], capture_output=True, text=True, check=False)
    assert bad.returncode == 2


GOOD = dict.fromkeys(FIELDS) | {"version": 1}


@pytest.mark.parametrize(
    ("fp", "problem"),
    [
        (None, "no fingerprint"),
        ([], "no fingerprint"),
        ({k: v for k, v in GOOD.items() if k != "kernel"}, "missing field kernel"),
        (GOOD | {"slot": "e0"}, "unknown field 'slot'"),
        (GOOD | {"smt": "on"}, "smt is neither bool nor null"),
        (GOOD | {"version": True}, "version is neither int nor null"),
        (GOOD | {"version": 2}, "version is not 1"),
        (GOOD | {"lock": {"name": "uv.lock"}}, "lock is not {name, sha256}"),
    ],
)
def test_problems_name_what_is_wrong(fp: object, problem: str):
    assert problem in problems(fp)


def test_unknown_values_are_null_not_missing():
    assert problems(GOOD) == []


@given(st.sets(st.integers(0, 300), min_size=1))
def test_cpu_lists_parse_as_linux_writes_them(cpus: set[int]):
    ranges, run = [], []
    for c in sorted(cpus):
        if run and c != run[-1] + 1:
            ranges.append(run)
            run = []
        run.append(c)
    ranges.append(run)
    text = ",".join(f"{r[0]}-{r[-1]}" if len(r) > 1 else str(r[0]) for r in ranges)
    assert fpmod._cpus(text) == cpus  # noqa: SLF001
