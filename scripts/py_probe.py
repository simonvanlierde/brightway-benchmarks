#!/usr/bin/env python3
"""Does Brightway install, import and score on Python PYTHON? Outside the asv harness.

Usage: py_probe.py PYTHON OUT_DIR

Makes a fresh venv for PYTHON with uv, installs each of PACKAGES into it on its own (so one that
does not resolve leaves the others' steps on record), then runs this file inside the venv, which
imports each package's modules and computes one score on a two-process system. Writes
OUT_DIR/probe.json (one entry per step) and OUT_DIR/requirements.txt, and exits 1 if any step failed.

A package none of whose releases declares PYTHON is not a failure: its install step says
`"declared": false`, and its imports (and, for brightway25, the score) are left out.

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

# What a user installs (compat.sh's `latest` column), each on its own, and the modules each brings.
PACKAGES = {
    "brightway25": ("bw2data", "bw2calc", "bw2io", "bw_processing", "matrix_utils"),
    "bw_graph_tools": ("bw_graph_tools",),
    "bw_timex": ("bw_timex",),
}
# uv's words when a requirement's own requires-python excludes the Python; with --no-deps nothing
# else can, so a network error or a missing package never reads as "not declared".
EXCLUDED = "the current Python version"
# Process a takes 2 kg of b; a emits 1 kg CO2 and b 3 kg, at 2 points per kg: (1 + 2 * 3) * 2.
SCORE = 14.0
# Seconds for one uv call or the inner run, so a stalled download leaves a failed step on record.
TIMEOUT = 600


def last_line(text: str) -> str:
    """The last non-empty line of TEXT, where a traceback names its error."""
    lines = [line for line in text.strip().splitlines() if line.strip()]
    return lines[-1] if lines else ""


def score() -> float:
    """The score of a on the two-process system, in a throwaway Brightway directory."""
    import bw2calc as bc  # noqa: PLC0415 - imported after BRIGHTWAY2_DIR is set
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


def inside(undeclared: list[str]) -> list[dict]:
    """The import and score steps, run in the probed Python, less those of UNDECLARED packages."""
    steps = []
    for module in (m for package, modules in PACKAGES.items() if package not in undeclared for m in modules):
        try:
            __import__(module)
        except Exception as e:  # noqa: BLE001 - any import error is the finding
            steps.append({"step": f"import {module}", "ok": False, "error": f"{type(e).__name__}: {e}"})
        else:
            steps.append({"step": f"import {module}", "ok": True})
    if "brightway25" in undeclared:
        return steps
    try:
        got = score()
    except Exception as e:  # noqa: BLE001
        steps.append({"step": "score", "ok": False, "error": f"{type(e).__name__}: {e}"})
    else:
        ok = abs(got - SCORE) <= 1e-9 * SCORE
        steps.append({"step": "score", "ok": ok, **({} if ok else {"error": f"score {got}, expected {SCORE}"})})
    return steps


def run(*args: str, env: dict | None = None, stdin: str | None = None) -> subprocess.CompletedProcess:
    """ARGS's result, output captured; a timeout is exit code -1 with the reason on stderr."""
    try:
        return subprocess.run(  # noqa: S603 - uv and the venv's python
            args,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            env=env,
            input=stdin,
            timeout=TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(args, -1, "", f"timed out after {TIMEOUT} s")


def probe(python: str, out: Path) -> list[dict]:
    """Every step for PYTHON; writes OUT/requirements.txt along the way."""
    venv = Path(tempfile.mkdtemp(prefix=f"py-probe-{python}-"))
    try:
        made = run("uv", "venv", "--quiet", "--python", python, str(venv / "v"))
        if made.returncode:
            return [{"step": "venv", "ok": False, "error": " ".join(made.stderr.split())}]
        py = venv / "v" / "bin" / "python"
        if not py.exists():
            py = venv / "v" / "Scripts" / "python.exe"  # a Windows venv
        steps, undeclared = [], []
        for package in PACKAGES:
            done = run("uv", "pip", "install", "--quiet", "--python", str(py), package)
            steps.append({"step": f"install {package}", "ok": not done.returncode})
            if not done.returncode:
                continue
            # Does any release of the package itself admit this Python? Its dependencies aside.
            alone = run("uv", "pip", "compile", "--quiet", "--no-deps", "--python", str(py), "-", stdin=package)
            if alone.returncode and EXCLUDED in " ".join(alone.stderr.split()):
                steps[-1].update(ok=True, declared=False)  # not this Python's fault: nothing claims it
                undeclared.append(package)
            else:
                steps[-1]["error"] = " ".join(done.stderr.split())  # uv wraps its reason over several lines
        (out / "requirements.txt").write_text(run("uv", "pip", "freeze", "--python", str(py)).stdout)
        (venv / "bw").mkdir()  # bw2data refuses a BRIGHTWAY2_DIR that does not exist
        env = {**os.environ, "BRIGHTWAY2_DIR": str(venv / "bw")}
        # -I drops PYTHONUTF8, so on Windows the inner Python would write cp1252 without -X utf8.
        inner = run(str(py), "-I", "-X", "utf8", __file__, "--inside", *undeclared, env=env)
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
        mark = "FAIL" if not s["ok"] else "ok  " if s.get("declared", True) else "skip"
        note = (
            f": {s['error']}" if "error" in s else "" if s.get("declared", True) else f": no release declares {python}"
        )
        print(f"{mark} {s['step']}{note}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    if sys.argv[1:2] == ["--inside"]:
        with contextlib.redirect_stdout(sys.stderr):  # Brightway prints progress; stdout carries the JSON
            steps = inside(sys.argv[2:])
        print(json.dumps(steps))
    elif len(sys.argv) == 3:
        sys.exit(main(sys.argv[1], Path(sys.argv[2])))
    else:
        sys.exit(__doc__)
