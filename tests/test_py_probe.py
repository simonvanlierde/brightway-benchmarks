"""scripts/py_probe.py with uv stubbed out: what it records for each step."""

import importlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from types import ModuleType

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"

# Logs each call with the config it saw, after sleeping $SLEEP seconds if set. `uv venv DIR` makes a
# python that prints $INSIDE (the inside steps' JSON) and, on stderr, its Brightway directory if that
# exists; installing bw_timex fails with a reason uv wraps over two lines.
UV = """#!/bin/sh
echo "$* config=${UV_NO_CONFIG-on} cutoff=${UV_EXCLUDE_NEWER-unset}" >>"$LOG"
[ -z "${SLEEP-}" ] || exec sleep "$SLEEP"
case "$1 $2" in
"pip install")
    for a; do :; done
    [ "$a" != bw_timex ] && exit 0
    printf 'x No solution found:\\n  Because Python 3.9 does not satisfy\\n  Python>=3.11\\n' >&2
    exit 1
    ;;
"pip freeze") echo "bw2data==4.8" ;;
venv*)
    for a; do venv=$a; done
    mkdir -p "$venv/bin"
    printf '#!/bin/sh\\nprintf "%%s" "$INSIDE"\\n' >"$venv/bin/python"
    echo '[ -d "$BRIGHTWAY2_DIR" ] && echo "BRIGHTWAY2_DIR=$BRIGHTWAY2_DIR" >&2' >>"$venv/bin/python"
    chmod +x "$venv/bin/python"
    ;;
esac
"""


@pytest.fixture
def probe(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    (tmp_path / "bin").mkdir()
    (tmp_path / "bin" / "uv").write_text(UV)
    (tmp_path / "bin" / "uv").chmod(0o755)
    monkeypatch.setenv("PATH", f"{tmp_path / 'bin'}:/usr/bin:/bin")
    monkeypatch.setenv("LOG", str(tmp_path / "log"))
    monkeypatch.setenv("UV_EXCLUDE_NEWER", "1 week")
    monkeypatch.setenv("UV_NO_CONFIG", "0")  # so teardown undoes main()'s own setting
    monkeypatch.syspath_prepend(str(SCRIPTS))
    return importlib.import_module("py_probe")


def test_records_each_step_and_fails_on_any(probe: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    inside = [
        {"step": "import bw2data", "ok": True},
        {"step": "import bw_graph_tools", "ok": False, "error": "TypeError: unsupported operand"},
        {"step": "score", "ok": True},
    ]
    monkeypatch.setenv("INSIDE", json.dumps(inside))
    out = tmp_path / "out"
    assert probe.main("3.9", out) == 1
    result = json.loads((out / "probe.json").read_text())
    assert result["python"] == "3.9"
    assert not result["ok"]
    steps = {s["step"]: s for s in result["steps"]}
    assert steps["install brightway25"] == {"step": "install brightway25", "ok": True}
    # uv's whole reason, on one line, not just its last wrapped line.
    assert steps["install bw_timex"]["error"] == "x No solution found: Because Python 3.9 does not satisfy Python>=3.11"
    assert steps["import bw_graph_tools"]["error"] == "TypeError: unsupported operand"
    assert (out / "requirements.txt").read_text() == "bw2data==4.8\n"
    # Today's releases: no cutoff, no project config.
    log = (tmp_path / "log").read_text().splitlines()
    assert log
    assert all("config=1 cutoff=unset" in line for line in log)


def test_green_when_every_step_passes(probe: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("INSIDE", json.dumps([{"step": "score", "ok": True}]))
    (tmp_path / "bin" / "uv").write_text(UV.replace("bw_timex", "none"))
    assert probe.main("3.13", tmp_path / "out") == 0


def test_inside_output_that_is_not_json_is_a_failed_step(
    probe: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("INSIDE", "Segmentation fault")
    step = probe.probe("3.13", tmp_path)[-1]
    # The fake python's stderr names the Brightway directory bw2data reads, which exists: a throwaway one.
    assert step["step"] == "probe"
    assert not step["ok"]
    assert step["error"].startswith(f"BRIGHTWAY2_DIR={tempfile.gettempdir()}")
    assert step["error"].endswith("bw")


def test_inside_records_import_errors_and_a_wrong_score(probe: ModuleType, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(probe, "MODULES", ("json", "no_such_module_here"))
    monkeypatch.setattr(probe, "score", lambda: 13.0)
    steps = probe.inside()
    assert steps[0] == {"step": "import json", "ok": True}
    assert steps[1]["error"].startswith("ModuleNotFoundError")
    assert steps[2] == {"step": "score", "ok": False, "error": "score 13.0, expected 14.0"}
    assert "no_such_module_here" not in sys.modules


def test_a_stalled_uv_call_is_a_failed_step(probe: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(probe, "TIMEOUT", 1)
    monkeypatch.setenv("SLEEP", "5")
    assert probe.probe("3.13", tmp_path) == [{"step": "venv", "ok": False, "error": "timed out after 1 s"}]


def test_inside_keeps_stdout_for_the_json(tmp_path: Path):
    # A bw2data that prints on import, as Brightway's progress messages do.
    (tmp_path / "bw2data").mkdir()
    (tmp_path / "bw2data" / "__init__.py").write_text('print("Writing activities")\n')
    (tmp_path / "bw").mkdir()
    env = {"PYTHONPATH": str(tmp_path), "BRIGHTWAY2_DIR": str(tmp_path / "bw"), "PATH": "/usr/bin:/bin"}
    done = subprocess.run(
        [sys.executable, SCRIPTS / "py_probe.py", "--inside"], capture_output=True, text=True, check=True, env=env
    )
    steps = json.loads(done.stdout)
    assert {"step": "import bw2data", "ok": True} in steps
    assert steps[-1]["step"] == "score"
    assert "Writing activities" in done.stderr
