"""bw2data #290: a SQLite project against sentier-brightway's Parquet registry.

Writes one synthetic system both ways from the same ``BuildResult`` and prints one JSON
line per format: write time, bytes on disk, the first score in a fresh Python process
(imports timed apart from the work), and the score against the float64 reference.
Synthetic data only, so the Sentier data licences do not apply. Run it with
``just registry-vs-sqlite`` (in the box, never on the host).
"""

import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from bwbench import temporary_brightway_dir
from bwbench.synth import SIZES, as_bw2data, generate

METHOD_KEY = ("synthetic", "method 0")
METHOD_ID = "synthetic:method-0"

COLD = r"""
import json, sys, time
t0 = time.perf_counter()
fmt, where = sys.argv[1], sys.argv[2]
if fmt == "sqlite":
    import bw2calc as bc, bw2data as bd
    t1 = time.perf_counter()
    bd.projects.set_current(where)
    node = bd.get_node(database="synthetic", code="p0")
    fu, objs, _ = bd.prepare_lca_inputs({node: 1}, method=("synthetic", "method 0"))
    lca = bc.LCA(fu, data_objs=objs)
    lca.lci()
    lca.lcia()
    score = lca.score
else:
    from sentier_brightway.datapackage import score as registry_score
    t1 = time.perf_counter()
    score = registry_score(where, "p0", "synthetic:method-0")
t2 = time.perf_counter()
print(json.dumps({"import_s": t1 - t0, "first_score_s": t2 - t1, "score": float(score)}))
"""


def build_result(size: str) -> tuple[object, float]:
    """The synthetic system as a sentier-brightway ``BuildResult``, plus its reference score."""
    from sentier_brightway.build import BoundMethod, BuildResult  # noqa: PLC0415
    from sentier_brightway.constants import BIOSPHERE_DB  # noqa: PLC0415
    from sentier_brightway.report import Coverage  # noqa: PLC0415

    system = generate(SIZES[size])
    bio, tech, cfs = as_bw2data(system, db="synthetic", bio=BIOSPHERE_DB)
    method = BoundMethod(
        key=METHOD_KEY,
        unit="kg",
        description="synthetic",
        method_id=METHOD_ID,
        cfs=tuple((tuple(key), value) for key, value in cfs[0]),
    )
    coverage = Coverage(
        flows_used=0,
        flows_mapped=0,
        exchange_rows=0,
        exchange_rows_mapped=0,
        residual_by_compartment=(),
        processes=len(tech),
        methods=1,
    )
    result = BuildResult(
        biosphere=bio,
        residual={},
        inventory=tech,
        methods=(method,),
        coverage=coverage,
        source="synthetic",
        inventory_db="synthetic",
        residual_db="synthetic-residual",
    )
    return result, system.reference_scores(1)[0][0]


def disk_bytes(path: Path) -> int:
    """Bytes in all files under ``path``."""
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file())


def cold(fmt: str, where: str) -> dict:
    """The first score in a fresh process, as someone opening the data would get it."""
    t = time.perf_counter()
    out = subprocess.run(  # noqa: S603 - fixed interpreter and arguments
        [sys.executable, "-c", COLD, fmt, where], capture_output=True, text=True, check=True
    )
    return json.loads(out.stdout.splitlines()[-1]) | {"process_s": time.perf_counter() - t}


def main() -> None:  # noqa: D103 - the module docstring is the usage
    size = sys.argv[1] if len(sys.argv) > 1 else "smoke"
    temporary_brightway_dir()
    import bw2data as bd  # noqa: PLC0415
    from sentier_brightway.datapackage import PACKAGE_DIR, REGISTRY_DIR, write_datapackages  # noqa: PLC0415
    from sentier_brightway.registry import build_registry, write_registry  # noqa: PLC0415
    from sentier_brightway.writer import write  # noqa: PLC0415

    result, ref = build_result(size)
    rows = []

    t = time.perf_counter()
    write(result, "synthetic")
    write_s = time.perf_counter() - t
    rows.append(
        {"format": "sqlite", "write_s": write_s, "bytes": disk_bytes(Path(bd.projects.dir))}
        | cold("sqlite", "synthetic")
    )

    out = Path(tempfile.mkdtemp(prefix="registry-"))
    t = time.perf_counter()
    registry = build_registry(result)
    write_registry(registry, out / REGISTRY_DIR)
    write_datapackages(registry, out / PACKAGE_DIR)
    write_s = time.perf_counter() - t
    rows.append({"format": "registry", "write_s": write_s, "bytes": disk_bytes(out)} | cold("registry", str(out)))

    versions = {m: __import__(m).__version__ for m in ("bw2data", "bw2calc", "bw_processing", "sentier_brightway")}
    for row in rows:
        row |= {"size": size, "reference": ref, "relative_error": abs(row["score"] - ref) / abs(ref), **versions}
        print(json.dumps(row))
    if rows[0]["score"] != rows[1]["score"]:
        print(f"scores differ: relative {abs(rows[0]['score'] - rows[1]['score']) / abs(ref):.1e}", file=sys.stderr)


if __name__ == "__main__":
    main()
