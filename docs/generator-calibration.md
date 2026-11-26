# Calibrating activity families

Generator v5 keeps regional variants of an activity in one family. Members copy the family's
supplier list. A supplier with a member in the consumer's region can be replaced by that
member. Members that nobody buys from sell to a later regional market or its global member.
This keeps shared input lists that degree distributions alone do not describe.

Family sizes use fixed quantiles of a capped Zipf distribution. Input counts use rounded
lognormal quantiles within bands of similar family size, each spanning a factor of two.
The generator shuffles both sets of quantiles. These are finite empirical distributions:
a band's population limits its tails, and a band with one family gets the median input
count. Only the declared `ecoinvent` size is calibrated. Other sizes scale the recipe.

The fitted settings retain their full precision. Rounding a setting can move an input count
across an integer boundary and change later random draws. The smoke hash and four-seed
calibration tests protect that boundary.

## Choosing the search

We compared candidates on seeds 0 to 3 using Bayesian optimisation, population search and
targeted checks. Errors were scaled by the existing test tolerances. For the integer consumer
q90 guard, a continuous guide measured the share of suppliers with at least 12 consumers.
This resolved a search plateau without changing any acceptance threshold. Candidates also
needed mean METIS fill and an actual SuperLU COLAMD factorization of Aᵀ to pass.

[Gutmann and Corander](https://www.jmlr.org/papers/v17/15-017.html) use a surrogate of simulator
discrepancy to choose evaluations adaptively.
[Common random numbers](https://arxiv.org/abs/1910.09259) support comparisons on fixed seeds.
Neither guarantees that a generator can meet its targets. A neural posterior was unnecessary:
the required output was one passing configuration.

[Ng et al. (2026)](https://arxiv.org/html/2608.03716v1) generate synthetic supply networks and
adaptively fit weights on a fixed graph. Their method supports staged calibration, but does
not establish LCI supplier overlap or sparse-factorization fill.

## Spreading supplier degree raises fill

Over seeds 0 to 3, v5 passes every per-seed guard, but two sit near a bound: consumers per
supplier q90 is 12 against 16 (the guard allows 11.2), and mean METIS fill is 37.9 against a
cap of 38.7. Two changes to the degree model reach the consumer target, and both raise fill.
In the first, later family members replace a share of their copied inputs with their own
draws. Mapped like copies, a share of 0.1 to 0.5 leaves q90 at 12 to 12.5 and raises METIS
to 42 to 51. Kept as drawn, q90 reaches 14 to 18, but METIS rises to 89 to 149. In the
second, a copy bound for a supplier family's global member goes instead, at some chance, to
the family's member for the consumer's continent. With 2 to 8 continents, q90 is 14 to 26
and METIS is 42 to 81. When the chance is 1, the largest loop shrinks from 0.62 to between
0.12 and 0.27 of the products, and a larger `back` does not bring it back. Every supplier
edge that does not follow the family template adds fill, so v5 stays the default.

## Holdout seeds 4 to 11

Five of these eight full-size v5 runs passed every structural guard. Seeds 4 and 11 had a
consumer-count q90 of 11, below the lower bound of 11.2. Seed 5 had an input-count q90 of
31, above the upper bound of 30.8. Consumer-count q90 ranged from 11 to 12 across the
holdout seeds, compared with the target of 16.

Mean METIS fill was 38.36, below the mean cap of 38.65. COLAMD fill on Aᵀ ranged from
28.92 to 35.12, within the upper bound used for seed 0. The holdout sweep records
these fill measurements separately from its structural pass count.

## Keeping fill explicit

[Small recursive separators help control sparse-factorization fill](https://simons.berkeley.edu/sites/default/files/docs/787/gilbertslides.pdf).
Matching degrees or sector shares alone does not establish realistic solver workloads.
A [microcanonical stochastic block model](https://arxiv.org/abs/1610.02703) can preserve
specified degrees and block constraints, but these do not prescribe shared supplier lists
or elimination fill. No measured improvement justified replacing the family construction
with another block model or an ERGM.

`tests/test_measure.py` is the acceptance check. It checks structural statistics over seeds
0 to 3, mean loop and negative-input shares, mean METIS fill, and COLAMD fill on Aᵀ.
The sweep below records per-seed statistics; a passing sweep alone does not establish the fill or
across-seed mean checks. Input magnitudes remain
less dispersed than the calibration data, so passing these guards does not reproduce every
property of a real database.

## Checking the profile with the sweep

`scripts/calibration_sweep.py` measures the `ecoinvent` profile at full size over several
seeds and judges each against the calibration guards. Its one case, `baseline`, is the
registered profile; a generator change under test adds a case to `CASES` with the profile
overrides it needs. Only aggregate statistics are written; it does not read a licensed database.
The report records each case's overrides, resolved profile, seed and NumPy/SciPy versions.

### Measurements and guards

By default, the command runs every case at seeds 0–3. Each case/seed runs in a fresh
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
`test_ecoinvent_profile_fills_like_its_target`, which the profile meets from generator v5 (#54).

### Running a sweep

Run full-size measurements in the repository's container (`scripts/box.sh`) on a quiet machine
with pinned CPUs and one thread per process. Mount a copy of the reviewed source read-only, not
an editable worktree, and keep the script that starts the run outside any folder the container
can write. A full sweep needs about 120 minutes.

Inside the container, with the source mounted read-only at `/src` and a writable output
folder at `/out`, run:

```sh
PYTHONPATH=src uv run --no-project --python 3.13 \
  --with numpy==2.5.4 --with scipy==1.18.1 --with pymetis==2025.2.2 \
  python scripts/calibration_sweep.py --output /out/calibration-sweep.json
```

`--cases baseline` or `--seeds 0 1` selects a smaller experiment. `--products 100` is a
small development fixture; the full target guards still apply, so it is not a passing
calibration run. There is no parallel-worker option.

### Reading failures

The JSON report is replaced atomically after each case/seed. While work is outstanding,
`complete` and `passed` remain false. A finished report has:

- `complete: true` only when every requested pair returned a valid measurement record.
- `passed: true` only when the report is complete and every calibration guard passes.
- Per-result `failures` for rejected calibration guards, or `error` for a crashed worker,
  malformed result or missing measurement.

A rejected configuration can therefore produce `complete: true`, `passed: false`. The command
exits 1 in that case. Worker failures and missing seeds also exit 1, with the partial report
preserved. A killed parent leaves its last report explicitly incomplete.

Keep the Python or container exit status in whatever starts the run. Redirect the log directly, or
use a shell with `set -o pipefail` when piping through `tee`. A log file or a complete result
table is not itself evidence that the calibration passed. Keep this sweep's artifacts
separate from the published benchmark histories.
