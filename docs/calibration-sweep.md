# Checking experimental input-sharing controls

`scripts/calibration_sweep.py` compares the current `ecoinvent` profile with three explicit
experimental configurations. It does not change the generator or calibrate new parameters.
Only aggregate statistics are written; it does not read a licensed database.

| Case | Overrides |
| --- | --- |
| `baseline` | None; the experimental controls retain their disabled defaults. |
| `sector` | `markets=0.95`, `market_by="sector"` |
| `copied` | `copy_long=0.85`, `market_by="sector"`; markets remain disabled. |
| `copied-sector` | `markets=0.95`, `market_by="sector"`, `copy_long=0.85` |

These are controlled comparisons, not a reconstruction of an earlier untracked experiment.
The report records each case's overrides, resolved profile, seed and NumPy/SciPy versions.

## Measurements and guards

By default, the command runs all four cases at seeds 0–3. Each case/seed runs in a fresh
process, serially. At most one LU factorization is retained at a time. It records:

- Structural statistics, including SCC size, locality and supplier overlap by degree band.
- Input-list overlap by list length, including each column's production entry. This measures
  shared supplier pairs on the input-list side; it is separate from supplier-row overlap.
- COLAMD fill and factorization wall time for the column-normalized matrix and its transpose.

The calibration guards are the per-seed ones of
`tests/test_measure.py::test_ecoinvent_profile_matches_its_target`, and the same guards apply
to every seed. The giant loop's share and the negative share vary by seed (SD 0.04 and 0.012),
so each seed gets 3 SD: 0.12 and 0.035. The test also holds the mean of seeds 0 to 3 to 3 SD
over the square root of four (0.06 and 0.02); the sweep reports per seed only. LU fill and
overlap are measurements here, not pass thresholds. The fill target is
`test_ecoinvent_profile_fills_like_its_target`, which the profile does not meet yet (#54).

## Running a sweep

Run full-size measurements only in the benchmark queue on a pinned machine, using the
repository's pinned container. Stage an immutable copy of the reviewed source first; do not
point a queued job at an editable worktree. Keep the executable job in the external
`brightway-benchmarks-box-queue/queue/backlog/` directory, outside container-writable mounts.
Use an initial 120-minute budget and preserve the runner's CPU-slot and one-thread settings.

Inside the container, with the source mounted read-only at `/src` and a writable output
folder at `/out`, run:

```sh
PYTHONPATH=src uv run --no-project --python 3.12 \
  --with numpy==2.5.3 --with scipy==1.18.1 --with pymetis==2025.2.2 \
  python scripts/calibration_sweep.py --output /out/calibration-sweep.json
```

`--cases baseline sector` or `--seeds 0 1` selects a smaller experiment. `--products 100` is a
small development fixture; the full target guards still apply, so it is not a passing
calibration run. There is no parallel-worker option.

## Reading failures

The JSON report is replaced atomically after each case/seed. While work is outstanding,
`complete` and `passed` remain false. A finished report has:

- `complete: true` only when every requested pair returned a valid measurement record.
- `passed: true` only when the report is complete and every calibration guard passes.
- Per-result `failures` for rejected calibration guards, or `error` for a crashed worker,
  malformed result or missing measurement.

A rejected configuration can therefore produce `complete: true`, `passed: false`. The command
exits 1 in that case. Worker failures and missing seeds also exit 1, with the partial report
preserved. A killed parent leaves its last report explicitly incomplete.

Preserve the Python/container exit status in the queue job. Redirect the log directly, or
use a shell with `set -o pipefail` when piping through `tee`. A log file or a complete result
table is not itself evidence that the calibration passed. Keep this sweep's artifacts
separate from the published benchmark histories.
