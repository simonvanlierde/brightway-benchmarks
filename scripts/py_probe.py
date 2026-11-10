#!/usr/bin/env python3
"""Does Brightway install, import and score on Python PYTHON? Outside the asv harness.

Usage: py_probe.py PYTHON OUT_DIR

Makes a fresh venv for PYTHON with uv, installs each of PACKAGES into it on its own (so one that
does not resolve leaves the others' steps on record), then runs this file inside the venv, which
imports each of MODULES and computes one score on a two-process system. Writes OUT_DIR/probe.json
(one entry per step) and OUT_DIR/requirements.txt, and exits 1 if any step failed.

The part that runs inside the venv must parse on the oldest Python probed (3.9).
"""

from __future__ import annotations

import contextlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# What a user installs (compat.sh's `latest` column), each on its own.
PACKAGES = ("brightway25", "bw_graph_tools", "bw_timex")
MODULES = ("bw2data", "bw2calc", "bw2io", "bw_processing", "matrix_utils", "bw_graph_tools", "bw_timex")
# Process a takes 2 kg of b; a emits 1 kg CO2 and b 3 kg, at 2 points per kg: (1 + 2 * 3) * 2.
SCORE = 14.0


def last_line(text: str) -> str:
    """The last non-empty line of TEXT, where a traceback names its error."""
    lines = [line for line in text.strip().splitlines() if line.strip()]
    return lines[-1] if lines else ""


def score() -> float:
    """The score of a on the two-process system, in a throwaway Brightway directory."""
    import bw2calc as bc  # noqa: PLC0415 - imported after BRIGHTWAY_DIR is set
    import bw2data as bd  # noqa: PLC0415  # ty: ignore[unresolved-import] - installed in the probed venv only

    bd.projects.set_current("probe")
    bd.Database("bio").write({("bio", "co2"): {"name": "CO2", "type": "emission", "unit": "kg"}})
    bd.Database("tech").write(
        {
            ("tech", "a"): {
                "name": "a",
                "unit": "kg",
                "exchanges": [
                    {"input": ("tech", "a"), "amount": 1, "type": "production"},
                    {"input": ("tech", "b"), "amount": 2, "type": "technosphere"},
                    {"input": ("bio", "co2"), "amount": 1, "type": "biosphere"},
                ],
            },
            ("tech", "b"): {
                "name": "b",
                "unit": "kg",
                "exchanges": [
                    {"input": ("tech", "b"), "amount": 1, "type": "production"},
                    {"input": ("bio", "co2"), "amount": 3, "type": "biosphere"},
                ],
            },
        }
    )
    method = bd.Method(("probe",))
    method.register()
    method.write([(("bio", "co2"), 2)])
    fu, data_objs, _ = bd.prepare_lca_inputs({bd.get_node(database="tech", code="a"): 1}, method=("probe",))
    lca = bc.LCA(fu, data_objs=data_objs)
    lca.lci()
    lca.lcia()
    return float(lca.score)


def inside() -> list[dict]:
    """The import and score steps, run in the probed Python."""
    steps = []
    for module in MODULES:
        try:
            __import__(module)
        except Exception as e:  # noqa: BLE001 - any import error is the finding
            steps.append({"step": f"import {module}", "ok": False, "error": f"{type(e).__name__}: {e}"})
        else:
            steps.append({"step": f"import {module}", "ok": True})
    try:
        got = score()
    except Exception as e:  # noqa: BLE001
        steps.append({"step": "score", "ok": False, "error": f"{type(e).__name__}: {e}"})
    else:
        ok = abs(got - SCORE) <= 1e-9 * SCORE
        steps.append({"step": "score", "ok": ok, **({} if ok else {"error": f"score {got}, expected {SCORE}"})})
    return steps


def run(*args: str) -> subprocess.CompletedProcess:
    """ARGS's result, output captured."""
    return subprocess.run(args, capture_output=True, text=True, check=False)  # noqa: S603 - uv and the venv's python


def probe(python: str, out: Path) -> list[dict]:
    """Every step for PYTHON; writes OUT/requirements.txt along the way."""
    venv = Path(tempfile.mkdtemp(prefix=f"py-probe-{python}-"))
    try:
        made = run("uv", "venv", "--quiet", "--python", python, str(venv / "v"))
        if made.returncode:
            return [{"step": "venv", "ok": False, "error": last_line(made.stderr)}]
        py = venv / "v" / "bin" / "python"
        if not py.exists():
            py = venv / "v" / "Scripts" / "python.exe"  # a Windows venv
        steps = []
        for package in PACKAGES:
            done = run("uv", "pip", "install", "--quiet", "--python", str(py), package)
            steps.append({"step": f"install {package}", "ok": not done.returncode})
            if done.returncode:
                steps[-1]["error"] = " ".join(done.stderr.split())  # uv wraps its reason over several lines
        (out / "requirements.txt").write_text(run("uv", "pip", "freeze", "--python", str(py)).stdout)
        env = {**os.environ, "BRIGHTWAY_DIR": str(venv / "bw")}
        inner = subprocess.run(  # noqa: S603
            [str(py), "-I", __file__, "--inside"], capture_output=True, text=True, check=False, env=env
        )
        try:
            steps += json.loads(inner.stdout)
        except ValueError:
            steps.append({"step": "probe", "ok": False, "error": last_line(inner.stderr) or "no output"})
        return steps
    finally:
        shutil.rmtree(venv, ignore_errors=True)


def main(python: str, out: Path) -> int:
    """Probe PYTHON, write OUT/probe.json, print a summary; 1 if a step failed."""
    out.mkdir(parents=True, exist_ok=True)
    # Releases a user installs today: no exclude-newer from pyproject.toml or the calling shell.
    os.environ["UV_NO_CONFIG"] = "1"
    os.environ.pop("UV_EXCLUDE_NEWER", None)
    steps = probe(python, out)
    result = {"python": python, "os": platform.system(), "ok": all(s["ok"] for s in steps), "steps": steps}
    (out / "probe.json").write_text(json.dumps(result, indent=1) + "\n")
    for s in steps:
        print(f"{'ok  ' if s['ok'] else 'FAIL'} {s['step']}" + (f": {s['error']}" if "error" in s else ""))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    if sys.argv[1:] == ["--inside"]:
        with contextlib.redirect_stdout(sys.stderr):  # Brightway prints progress; stdout carries the JSON
            steps = inside()
        print(json.dumps(steps))
    elif len(sys.argv) == 3:
        sys.exit(main(sys.argv[1], Path(sys.argv[2])))
    else:
        sys.exit(__doc__)
