"""bw2data #290: a SQLite project against sentier-brightway's Parquet registry.

Writes one synthetic system both ways from the same ``BuildResult`` and prints one JSON
line per format: write time, bytes on disk, the first score in a fresh Python process
(imports timed apart from the work), that process's peak resident memory, and the score against
the float64 reference (for SQLite, against ``System.float32_reference``: bw2data stores amounts
as float32). The registry is read three ways: sentier's ``score()`` (pandas loads every table, then its
``bw_package/`` datapackages), the same datapackages with the process looked up by DuckDB's
``read_parquet``, and the matrices built by DuckDB from the Parquet tables alone, without
``bw_package/``. It exits non-zero when any score is off by more than ``BW2DATA_RTOL``.
Synthetic data only, so the Sentier data licences do not apply. Run it with
``just registry-vs-sqlite`` (in the box, never on the host).
"""

import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from bwbench import BW2DATA_RTOL, check, temporary_brightway_dir
from bwbench.synth import system

METHOD_KEY = ("synthetic", "method 0")
METHOD_ID = "synthetic:method-0"

COLD = r"""
import json, sys, time
from bwbench import peak_rss_bytes
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
elif fmt == "registry":
    from sentier_brightway.datapackage import score as registry_score
    t1 = time.perf_counter()
    score = registry_score(where, "p0", "synthetic:method-0")
else:
    import bw2calc as bc, bw_processing as bwp, duckdb, numpy as np
    from sentier_brightway.datapackage import load_inventory_datapackage, load_method_datapackage
    t1 = time.perf_counter()
    reg = f"{where}/registry"
    con = duckdb.connect()
    # Only the column and row it needs, where sentier's score() loads every table with pandas.
    (bw_id,) = con.sql(f"SELECT bw_id FROM read_parquet('{reg}/processes.parquet') WHERE code = 'p0'").fetchone()
    if fmt == "registry-duckdb":
        objs = [load_inventory_datapackage(where), load_method_datapackage(where, "synthetic:method-0")]
    else:  # parquet-duckdb: the matrices from the registry's own tables, no bw_package/ folder
        def vector(dp, matrix, sql, flip=False):
            t = {k: np.asarray(v) for k, v in con.sql(sql).fetchnumpy().items()}
            idx = np.empty(len(t["data"]), dtype=bwp.INDICES_DTYPE)
            idx["row"], idx["col"] = t["row"], t["col"]
            kw = {"flip_array": t["flip"].astype(bool)} if flip else {}
            dp.add_persistent_vector(matrix=matrix, name=matrix, indices_array=idx, data_array=t["data"], **kw)

        dp = bwp.create_datapackage()
        ex = f"read_parquet('{reg}/exchanges.parquet')"
        vector(dp, "technosphere_matrix", f"SELECT input_bw_id AS row, process_bw_id AS col, amount AS data, "
               f"type = 'technosphere' AS flip FROM {ex} WHERE type IN ('production', 'technosphere')", flip=True)
        vector(dp, "biosphere_matrix", f"SELECT input_bw_id AS row, process_bw_id AS col, amount AS data "
               f"FROM {ex} WHERE type = 'biosphere'")
        vector(dp, "characterization_matrix", f"SELECT flow_bw_id AS row, flow_bw_id AS col, factor AS data "
               f"FROM read_parquet('{reg}/characterization-factors.parquet') WHERE method_id = 'synthetic:method-0'")
        objs = [dp]
    lca = bc.LCA({int(bw_id): 1.0}, data_objs=objs)
    lca.lci()
    lca.lcia()
    score = lca.score
t2 = time.perf_counter()
print(json.dumps({"import_s": t1 - t0, "first_score_s": t2 - t1, "score": float(score), "peak_rss": peak_rss_bytes()}))
"""


def build_result(size: str) -> tuple[object, float, float]:
    """The synthetic system as a sentier-brightway ``BuildResult``, plus its float64 and float32 reference scores."""
    from sentier_brightway.build import BoundMethod, BuildResult  # noqa: PLC0415
    from sentier_brightway.constants import BIOSPHERE_DB  # noqa: PLC0415
    from sentier_brightway.report import Coverage  # noqa: PLC0415

    synthetic = system(size)
    bio, tech, cfs = synthetic.bw2data(db="synthetic", bio=BIOSPHERE_DB)
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
    return result, synthetic.reference_scores(1)[0][0], synthetic.float32_reference()


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

    result, ref, ref32 = build_result(size)
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
    parquet_s = time.perf_counter() - t
    write_datapackages(registry, out / PACKAGE_DIR)
    write_s = time.perf_counter() - t
    rows.extend(
        {"format": fmt, "write_s": write_s, "bytes": disk_bytes(out)} | cold(fmt, str(out))
        for fmt in ("registry", "registry-duckdb")
    )
    # The registry's Parquet tables alone: no bw_package/ to write or store.
    rows.append(
        {"format": "parquet-duckdb", "write_s": parquet_s, "bytes": disk_bytes(out / REGISTRY_DIR)}
        | cold("parquet-duckdb", str(out))
    )

    modules = ("bw2data", "bw2calc", "bw_processing", "sentier_brightway", "duckdb")
    versions = {m: __import__(m).__version__ for m in modules}
    for row in rows:
        r = ref32 if row["format"] == "sqlite" else ref
        row |= {"size": size, "reference": r, "relative_error": abs(row["score"] - r) / abs(r), **versions}
        print(json.dumps(row))
    for row in rows:  # after printing them all, so a failure still shows the numbers
        check(row["score"], row["reference"], BW2DATA_RTOL, f"{row['format']} score")


if __name__ == "__main__":
    main()
