"""UMFPACK iterative refinement on and off, and SuperLU, per repeated solve on one machine.

    PYTHONPATH=src python scripts/refine_probe.py umfpack|superlu [SIZE] [RUNS]

Builds the synthetic system, factorizes once, then times ``lca.redo_lci({1: 1})`` RUNS times
(30 by default). For umfpack the runs alternate refinement on (UMFPACK's default) and off
(``UMFPACK_IRSTEP=0``) so machine drift hits both alike. Prints one JSON object.
"""

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

SOLVER = sys.argv[1]
if SOLVER == "superlu":
    sys.modules["scikits.umfpack"] = None  # as if not installed
    sys.modules["pypardiso"] = None
sys.modules["pypardiso"] = None

import bwbench  # noqa: E402, I001 - first, so the BLAS thread pin lands before numpy loads
import bw2calc as bc  # noqa: E402
from bwbench.synth import packages  # noqa: E402

warnings.simplefilter("ignore")
SIZE = sys.argv[2] if len(sys.argv) > 2 else "ecoinvent"
RUNS = int(sys.argv[3]) if len(sys.argv) > 3 else 30


def stats(times: list[float]) -> dict:
    q = statistics.quantiles(times, n=4)
    return {
        "median_ms": 1e3 * statistics.median(times),
        "iqr_ms": 1e3 * (q[2] - q[0]),
        "min_ms": 1e3 * min(times),
        "max_ms": 1e3 * max(times),
        "n": len(times),
    }


def sh(*cmd: str) -> str:
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
    raise SystemExit(f"bw2calc picked {picked}, not {SOLVER}")


def score() -> float:
    return float((lca.characterization_matrix @ lca.inventory).sum())


def solve() -> float:
    t0 = time.perf_counter()
    lca.redo_lci({1: 1})
    return time.perf_counter() - t0


solve()  # warm up
ref = refs[1][0]
out = {
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
    from scikits.umfpack import umfpack  # noqa: PLC0415

    out["scikit-umfpack"] = version("scikit-umfpack")
    cells = (c.cell_contents for c in getattr(lca.solver, "__closure__", None) or ())
    ctx = next(c for c in cells if type(c).__name__ == "UmfpackContext")
    irstep, taken = umfpack.umfDefines["UMFPACK_IRSTEP"], umfpack.umfDefines["UMFPACK_IR_TAKEN"]
    default_irstep = float(ctx.control[irstep])
    t = {"on": [], "off": []}
    steps = {"on": [], "off": []}
    scores = {}
    for _ in range(RUNS):
        for mode in ("on", "off"):
            ctx.control[irstep] = default_irstep if mode == "on" else 0.0
            t[mode].append(solve())
            steps[mode].append(float(ctx.info[taken]))
            scores[mode] = score()
    out["default_irstep"] = default_irstep
    out["on"] = stats(t["on"]) | {"steps_median": statistics.median(steps["on"]), "steps_max": max(steps["on"])}
    out["off"] = stats(t["off"]) | {"steps_median": statistics.median(steps["off"]), "steps_max": max(steps["off"])}
    out["speedup_median"] = out["on"]["median_ms"] / out["off"]["median_ms"]
    out["rel_err_on_vs_ref"] = abs(scores["on"] - ref) / abs(ref)
    out["rel_err_off_vs_ref"] = abs(scores["off"] - ref) / abs(ref)
    out["rel_diff_off_vs_on"] = abs(scores["off"] - scores["on"]) / abs(scores["on"])
    ext = list(Path(umfpack.__file__).parent.glob("*.so")) + list(Path(umfpack.__file__).parent.glob("*.dylib"))
    out["linked_libs"] = {e.name: sh("/usr/bin/otool", "-L", str(e)) for e in ext}
else:
    times = [solve() for _ in range(RUNS)]
    out["superlu"] = stats(times)
    out["rel_err_vs_ref"] = abs(score() - ref) / abs(ref)
try:
    from threadpoolctl import threadpool_info  # noqa: PLC0415

    out["threadpool"] = sorted({f"{p['internal_api']} {p['version']}" for p in threadpool_info()})
except ImportError:
    pass
print(json.dumps(out, indent=2))
