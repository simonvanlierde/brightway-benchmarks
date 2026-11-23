"""UMFPACK iterative refinement on and off, and SuperLU, per repeated solve on one machine.

    PYTHONPATH=src python scripts/refine_probe.py umfpack|superlu [SIZE] [RUNS]

Builds the synthetic system, factorizes once, then times ``lca.redo_lci({1: 1})`` RUNS times
(30 by default). For umfpack the runs pair refinement on (UMFPACK's default) and off
(``UMFPACK_IRSTEP=0``), reversing the order in each pair. Prints one JSON object.
"""

import argparse
import json
import os
import platform
import statistics
import subprocess
import sys
import time
import warnings
from importlib.metadata import version
from pathlib import Path

parser = argparse.ArgumentParser(description="Time repeated LCA solves with SuperLU or UMFPACK.")
parser.add_argument("solver", choices=("umfpack", "superlu"))
parser.add_argument("size", default="ecoinvent", nargs="?", help="benchmark profile (default: ecoinvent)")
parser.add_argument("runs", type=int, default=30, nargs="?", help="number of solves per mode (default: 30)")
args = parser.parse_args()
if args.runs < 1:
    parser.error("runs must be at least 1")
SOLVER, SIZE, RUNS = args.solver, args.size, args.runs
if SOLVER == "superlu":
    sys.modules["scikits.umfpack"] = None  # ty: ignore[invalid-assignment]
sys.modules["pypardiso"] = None  # ty: ignore[invalid-assignment]

import bwbench  # noqa: E402, I001 - first, so the BLAS thread pin lands before numpy loads
import bw2calc as bc  # noqa: E402
from bwbench.synth import packages  # noqa: E402

warnings.simplefilter("ignore")


def stats(times: list[float]) -> dict:
    """Summarize elapsed seconds in milliseconds."""
    q = statistics.quantiles(times, n=4) if len(times) > 1 else [times[0]] * 3
    return {
        "median_ms": 1e3 * statistics.median(times),
        "iqr_ms": 1e3 * (q[2] - q[0]),
        "min_ms": 1e3 * min(times),
        "max_ms": 1e3 * max(times),
        "n": len(times),
    }


def sh(*cmd: str) -> str:
    """Read optional platform information from a native command."""
    try:
        return subprocess.run(cmd, capture_output=True, text=True, check=False).stdout.strip()  # noqa: S603
    except OSError:  # otool and sysctl are macOS tools; the probe also runs on Linux
        return ""


inventory, methods, refs, _ = packages(SIZE)
lca = bc.LCA(demand={0: 1}, data_objs=[inventory, methods[0]])
lca.lci(factorize=True)
lca.lcia()
picked = "pypardiso" if bc.PYPARDISO else "umfpack" if bc.UMFPACK else "superlu"
if picked != SOLVER:
    msg = f"bw2calc picked {picked}, expected {SOLVER}"
    raise SystemExit(msg)


def score_error() -> tuple[float, float]:
    """Check the most recent solve outside its measured span."""
    score = float((lca.characterization_matrix @ lca.inventory).sum())
    return score, bwbench.check(score, ref, bwbench.DIRECT_RTOL, f"{SOLVER} score")


def solve() -> float:
    """Time the solve alone, with the factorization already available."""
    t0 = time.perf_counter()
    lca.redo_lci({1: 1})
    return time.perf_counter() - t0


solve()  # warm up
ref = refs[1][0]
out: dict[str, object] = {
    "solver": SOLVER,
    "size": SIZE,
    "runs": RUNS,
    "bw2calc": version("bw2calc"),
    "scipy": version("scipy"),
    "numpy": version("numpy"),
    "platform": f"{platform.system()} {platform.machine()}",
    "cpu": sh("sysctl", "-n", "machdep.cpu.brand_string") or platform.processor(),
    "cores": os.cpu_count(),
    "blas_threads": bwbench.THREADS,
}
if SOLVER == "umfpack":
    from scikits.umfpack import umfpack

    out["scikit-umfpack"] = version("scikit-umfpack")
    cells = (c.cell_contents for c in getattr(lca.solver, "__closure__", None) or ())
    ctx = next(c for c in cells if type(c).__name__ == "UmfpackContext")
    irstep, taken = umfpack.umfDefines["UMFPACK_IRSTEP"], umfpack.umfDefines["UMFPACK_IR_TAKEN"]
    default_irstep = float(ctx.control[irstep])
    if default_irstep <= 0:
        msg = "UMFPACK already has iterative refinement disabled"
        raise SystemExit(msg)
    t = {"on": [], "off": []}
    steps = {"on": [], "off": []}
    errors = {"on": [], "off": []}
    differences = []
    for pair in range(RUNS):
        scores = {}
        modes = ("on", "off") if pair % 2 == 0 else ("off", "on")
        for mode in modes:
            ctx.control[irstep] = default_irstep if mode == "on" else 0.0
            t[mode].append(solve())
            steps[mode].append(float(ctx.info[taken]))
            scores[mode], error = score_error()
            errors[mode].append(error)
        differences.append(bwbench.check(scores["off"], scores["on"], 2 * bwbench.DIRECT_RTOL, "paired scores"))
    out["default_irstep"] = default_irstep
    for mode in ("on", "off"):
        out[mode] = stats(t[mode]) | {"steps_median": statistics.median(steps[mode]), "steps_max": max(steps[mode])}
    out["speedup_median"] = statistics.median(t["on"]) / statistics.median(t["off"])
    out["rel_err_on_vs_ref"] = max(errors["on"])
    out["rel_err_off_vs_ref"] = max(errors["off"])
    out["rel_diff_off_vs_on"] = max(differences)
    ext = list(Path(umfpack.__file__).parent.glob("*.so")) + list(Path(umfpack.__file__).parent.glob("*.dylib"))
    out["linked_libs"] = {e.name: sh("/usr/bin/otool", "-L", str(e)) for e in ext}
else:
    times, errors = [], []
    for _ in range(RUNS):
        times.append(solve())
        errors.append(score_error()[1])
    out["superlu"] = stats(times)
    out["rel_err_vs_ref"] = max(errors)
try:
    from threadpoolctl import threadpool_info  # ty: ignore[import-not-found]

    out["threadpool"] = sorted({f"{p['internal_api']} {p['version']}" for p in threadpool_info()})
except ImportError:
    pass
print(json.dumps(out, indent=2))
