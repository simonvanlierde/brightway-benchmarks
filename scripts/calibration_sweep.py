"""Compare experimental input-sharing controls without changing the generator.

Each case/seed runs in a fresh process, with one COLAMD factorization alive at a time.
The JSON report is updated after every case; only a complete, passing report exits zero.
"""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
import time
from dataclasses import asdict
from importlib.metadata import version
from pathlib import Path
from typing import TYPE_CHECKING, Any

from scipy import sparse
from scipy.sparse import linalg as sla

from bwbench import synth

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

CASES = {
    "baseline": {},
    "sector": {"markets": 0.95, "market_by": "sector"},
    "copied": {"copy_long": 0.85, "market_by": "sector"},
    "copied-sector": {"markets": 0.95, "market_by": "sector", "copy_long": 0.85},
}
SEEDS = (0, 1, 2, 3)


def calibration_failures(got: synth.Stats, want: synth.Stats) -> list[str]:
    """Apply the existing ecoinvent calibration test's tolerances to every seed."""
    checks = [
        ("products", got.products, want.products, 0.0, 0.0),
        ("entries", got.entries, want.entries, 0.05, 0.0),
        ("inputs.q50", got.inputs_per_product["q50"], want.inputs_per_product["q50"], 0.0, 1.0),
        ("inputs.q90", got.inputs_per_product["q90"], want.inputs_per_product["q90"], 0.1, 0.0),
        ("inputs.q99", got.inputs_per_product["q99"], want.inputs_per_product["q99"], 0.3, 0.0),
        ("SCC share", got.loops["largest"] / got.products, want.loops["largest"] / want.products, 0.0, 0.03),
        ("negative input share", got.negative_input_share, want.negative_input_share, 0.0, 0.02),
        ("spectral radius", got.spectral_radius, want.spectral_radius, 0.0, 0.01),
        ("same location share", got.same_location_share, want.same_location_share, 0.0, 0.03),
        ("same sector share", got.same_sector_share, want.same_sector_share, 0.0, 0.03),
    ]
    checks.extend(
        (
            f"consumers.{q}",
            got.consumers_per_supplier[q],
            want.consumers_per_supplier[q],
            0.0 if q in {"q25", "q50"} else 0.3,
            0.0,
        )
        for q in ("q25", "q50", "q90", "q99")
    )
    return [
        f"{name}: got {actual}, target {target}, rel {rel}, abs {absolute}"
        for name, actual, target, rel, absolute in checks
        if actual is None
        or target is None
        or not math.isfinite(actual)
        or abs(actual - target) > max(rel * abs(target), absolute)
    ]


def measure_case(case: str, seed: int, products: int | None = None) -> dict[str, Any]:
    """Build and measure one case, then release its process before the next case."""
    overrides = CASES[case] | ({"products": products} if products is not None else {})
    system = synth.system("ecoinvent", seed=seed, **overrides)
    if system.region is None or system.sector is None:
        msg = "the calibration sweep requires region and sector labels"
        raise ValueError(msg)
    a = system.technosphere().tocsc()
    stats = synth.measure(a, [str(x) for x in system.region], [str(x) for x in system.sector], repeats=0)
    a = (a @ sparse.diags(1.0 / a.diagonal())).tocsc()
    fills, seconds = {}, {}
    for label, matrix in (("COLAMD", a), ("COLAMD (A^T)", a.T.tocsc())):
        start = time.perf_counter()
        lu = sla.splu(matrix, permc_spec="COLAMD")
        seconds[label] = time.perf_counter() - start
        fills[label] = float((lu.L.nnz + lu.U.nnz - matrix.shape[0]) / matrix.nnz)
        del lu
    data = asdict(stats) | {"lu_fill": fills, "factor_seconds": seconds}
    return {
        "case": case,
        "seed": seed,
        "overrides": overrides,
        "profile": asdict(system.profile),
        "stats": data,
        "input_overlap_by_band": input_overlap(a),
    }


def input_overlap(a: sparse.csc_matrix) -> dict[str, dict[str, float]]:
    """Input-list overlap: A columns, including production, grouped by their entry counts."""
    pattern = (a != 0).astype(float).tocsc()
    squares = (pattern.indptr[1:] - pattern.indptr[:-1]).astype(float) ** 2
    counts = pattern.indptr[1:] - pattern.indptr[:-1]
    result = {}
    for low, high in synth.OVERLAP_BANDS:
        selected = (counts >= low) & (counts <= high)
        pairs = float(squares[selected].sum())
        if pairs:
            band = pattern[:, selected]
            joined = band @ band.T
            label = f"{low}+" if high == synth.OVERLAP_BANDS[-1][1] else f"{low}-{high}"
            result[label] = {"overlap": float(joined.nnz / pairs), "pairs_share": pairs / float(squares.sum())}
            del joined
    return result


def checked_stats(row: dict[str, Any], case: str, seed: int, products: int | None = None) -> synth.Stats:
    """Reject wrong identities and missing or nonfinite measurements before counting a result."""
    if (row["case"], row["seed"]) != (case, seed):
        msg = f"worker returned another case or seed for {case}/{seed}"
        raise ValueError(msg)
    expected_overrides = CASES[case] | ({"products": products} if products is not None else {})
    expected_profile = asdict(synth.profile("ecoinvent", **expected_overrides))
    for name, expected in (("overrides", expected_overrides), ("profile", expected_profile)):
        if json.dumps(row[name], sort_keys=True) != json.dumps(expected, sort_keys=True):
            msg = f"worker {name} does not match the requested {case} configuration"
            raise ValueError(msg)
    stats = synth.Stats(**row["stats"])
    checked_overlap(row["input_overlap_by_band"], entries=stats.entries)
    if stats.products != expected_profile["products"]:
        msg = "measured product count does not match the requested profile"
        raise ValueError(msg)
    for name in ("COLAMD", "COLAMD (A^T)"):
        if not math.isfinite(stats.lu_fill[name]) or stats.lu_fill[name] <= 0:
            msg = f"invalid or missing {name} fill"
            raise ValueError(msg)
        if not math.isfinite(stats.factor_seconds[name]) or stats.factor_seconds[name] < 0:
            msg = f"invalid or missing {name} time"
            raise ValueError(msg)
    json.dumps(row, allow_nan=False)
    return stats


def checked_overlap(bands: dict[str, dict[str, float]], *, entries: int) -> None:
    """Reject incomplete or impossible input-list overlap measurements."""
    if entries > 0 and not bands:
        msg = "input overlap is missing although the matrix has inputs"
        raise ValueError(msg)
    labels = {f"{low}+" if high == synth.OVERLAP_BANDS[-1][1] else f"{low}-{high}" for low, high in synth.OVERLAP_BANDS}
    if not isinstance(bands, dict) or bands.keys() - labels:
        msg = "input overlap has an invalid degree band"
        raise ValueError(msg)
    for values in bands.values():
        if set(values) != {"overlap", "pairs_share"} or any(
            isinstance(value, bool) or not math.isfinite(value) or not 0 < value <= 1 for value in values.values()
        ):
            msg = "input overlap needs finite overlap and pairs_share in (0, 1]"
            raise ValueError(msg)
    if sum(values["pairs_share"] for values in bands.values()) > 1 + 1e-12:
        msg = "input overlap band shares exceed one"
        raise ValueError(msg)


def write_report(path: Path, report: dict[str, Any]) -> None:
    """Replace the report only after its complete JSON representation is written."""
    text = json.dumps(report, indent=2, allow_nan=False) + "\n"
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def run_sweep(
    cases: Sequence[str],
    seeds: Sequence[int],
    worker: Callable[[str, int], dict[str, Any]],
    target: synth.Stats,
    output: Path,
    products: int | None = None,
) -> dict[str, Any]:
    """Collect every requested pair; errors and failed guards remain visible and fail the run."""
    if not cases or not seeds or len(set(cases)) != len(cases) or len(set(seeds)) != len(seeds):
        msg = "a sweep needs nonempty, unique cases and seeds"
        raise ValueError(msg)
    report: dict[str, Any] = {
        "format_version": 1,
        "generator_version": synth.GENERATOR_VERSION,
        "versions": {name: version(name) for name in ("numpy", "scipy")},
        "cases": {name: CASES[name] for name in cases},
        "seeds": list(seeds),
        "target": asdict(target),
        "complete": False,
        "passed": False,
        "results": [],
    }
    write_report(output, report)
    expected = {(case, seed) for case in cases for seed in seeds}
    seen = set()
    for case in cases:
        for seed in seeds:
            try:
                row = worker(case, seed)
                stats = checked_stats(row, case, seed, products)
                row["failures"] = calibration_failures(stats, target)
                row["passed"] = not row["failures"]
                seen.add((case, seed))
            except Exception as exc:  # noqa: BLE001 - keep other requested seeds and the failed result
                error = f"{type(exc).__name__}: {exc}"
                if isinstance(exc, subprocess.CalledProcessError) and exc.stderr:
                    error += "\n" + exc.stderr[-4000:]
                row = {"case": case, "seed": seed, "passed": False, "error": error}
            report["results"].append(row)
            write_report(output, report)
    report["complete"] = seen == expected
    report["passed"] = report["complete"] and all(row["passed"] for row in report["results"])
    write_report(output, report)
    return report


def main(argv: Sequence[str] | None = None) -> int:
    """Write a complete or explicitly failed sweep; never infer success from a partial table."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("calibration-sweep.json"))
    parser.add_argument("--cases", choices=CASES, nargs="+", default=list(CASES))
    parser.add_argument("--seeds", type=int, nargs="+", default=list(SEEDS))
    parser.add_argument("--products", type=int, help="small development fixture; full target guards still apply")
    parser.add_argument("--worker", choices=CASES, help=argparse.SUPPRESS)
    parser.add_argument("--seed", type=int, default=0, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.products is not None and args.products < 2:
        parser.error("--products must be at least 2")
    if len(set(args.cases)) != len(args.cases) or len(set(args.seeds)) != len(args.seeds):
        parser.error("cases and seeds must not repeat")
    if any(seed < 0 for seed in args.seeds) or args.seed < 0:
        parser.error("seeds must be nonnegative")
    if args.worker:
        print(json.dumps(measure_case(args.worker, args.seed, args.products), allow_nan=False))
        return 0
    target_data = json.loads((synth.PROFILES_DIR / "ecoinvent-3.12-cutoff.json").read_text(encoding="utf-8"))

    def worker(case: str, seed: int) -> dict[str, Any]:
        command = [sys.executable, __file__, "--worker", case, "--seed", str(seed)]
        if args.products is not None:
            command.extend(["--products", str(args.products)])
        result = subprocess.run(command, capture_output=True, text=True, check=True)  # noqa: S603
        return json.loads(result.stdout)

    report = run_sweep(args.cases, args.seeds, worker, synth.Stats(**target_data["stats"]), args.output, args.products)
    print(f"{len(report['results'])} results; complete={report['complete']}; passed={report['passed']}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
