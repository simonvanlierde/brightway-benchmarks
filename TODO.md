# TODO

- [ ] Calibrate the `ecoinvent` profile over several seeds, not seed 0 only: one realization
      to the next moves the giant loop's share by about ten points (0.62 against 0.72 when a
      small parameter change shifted every later random draw), so the oracle test's 0.03
      band holds for seed 0 alone.
- [ ] Lower the `ecoinvent` profile's LU fill: COLAMD 323 and MMD_AT_PLUS_A 99, against
      ecoinvent's 175 and 76. `measure()` traces it to consumer overlap among the smaller
      suppliers: with the top 1% of supplier rows removed, nnz(A^T A) is 0.37 of the summed
      squared row counts in ecoinvent and 0.88 in the generator, while the hubs overlap alike
      (Jaccard 0.072 against 0.064). Per band of supplier size, ecoinvent's overlap is lowest
      for suppliers with 16 to 255 consumers (0.38 to 0.44 against 0.90 to 0.95), and 39% of its products copy
      another's input list (generator 11%). Regional hub bundles, consumer baskets, product
      families, exact input-list copies (47% copied, overlap unchanged) and locality settings
      did not move the mid bands. Next: measure how long the copied lists are, since short
      lists that agree by chance would explain the 39% without explaining the overlap.
- [ ] Run the six suites under pytest-codspeed: entry modules calling `bwbench.pytest.tests`,
      and a runner image (a spike ran traversal under CPU simulation; not in the repo yet).
- [ ] `asv.sh` still names machines after the container hostname by default, which includes
      the host's name. `just results-commit` refuses such results; a neutral default
      (for example the slot name) would save a rerun.
- [ ] Setups solve once before the timed call (a warm-up and early check), on the same
      datapackage objects, so "first score" is warm. Time a cold `run()` on fresh packages
      against it in the box and decide whether to drop the warm-up at 25k products and up.
- [ ] Check that pytest-codspeed's `pedantic` calls the target once per setup under CPU
      simulation; a warm-up call would trip the seam's "run called twice" guard.
- [ ] Measure the noise of SuperLU and UMFPACK at the ecoinvent size (only PyPardiso's is
      measured), once per release in the backfill rather than as repeats.
- [ ] Backfill the other packages on the pinned benchmark machine, in one fixed CPU slot,
      with `BWBENCH_SIZES=ecoinvent,exiobase` (bw2calc is done at `ecoinvent`).
- [ ] Recheck the last single-round bw2calc outlier with `BWBENCH_ROUNDS=2`: 2.2 with SuperLU
      `IterativeLCA` (29.3 against 27.7 s). 2.0.2 SuperLU and 2.1.1 PyPardiso were rerun on
      2026-10-18 and came back in line (27.8 and 10.0 s).
- [ ] First publication: `git push origin results` and `gh workflow run site.yml` (Pages is
      on, deploying from `main` only).
- [ ] Drop the `versions-*.txt` files once the pins check below has run: the lock files
      hold the same versions.
- [ ] The site job builds the box image and clones six upstream repos on every run, though
      `asv publish` only reads results. Run asv there directly, or cache `.asv/`, once the
      first runs show how long it takes. CodSpeed, if added, runs on `pull_request` only.
- [ ] Run `just registry-vs-sqlite ecoinvent` on the benchmark machine: does the SQLite path's 3e-8
      score error hold at size?

## Verify in the box

Checked on the benchmark machine on 2026-10-13: the read-only mount (plain docker, and oss-bench through `OSS_BENCH_RW`), `just smoke`,
the PyPardiso reset (4.32 ms against 3.18 ms at `cfad4bf`), the lock and the image tag.
Still open:

- [ ] Pins hold: run `just smoke` on another day and `diff` `.asv/smoke/*/smoke/versions-*.txt`
      against the copies in `.asv/versions-2026-10-13/`. Also check old releases in a full
      `just bench bw2calc`: a versions file showing another numpy means pip replaced the pin.
