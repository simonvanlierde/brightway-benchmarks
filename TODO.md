# TODO

- [ ] Lower the `ecoinvent` profile's LU fill: COLAMD 323 and MMD_AT_PLUS_A 99, against
      ecoinvent's 175 and 76. `measure()` traces it to consumer overlap among the smaller
      suppliers: with the top 1% of supplier rows removed, nnz(A^T A) is 0.37 of the summed
      squared row counts in ecoinvent and 0.88 in the generator, while the hubs overlap alike
      (Jaccard 0.072 against 0.064). Per band of supplier size, ecoinvent's overlap is lowest
      at 17-256 consumers (0.38 to 0.44 against 0.90 to 0.95), and 39% of its products copy
      another's input list (generator 11%). Regional hub bundles, consumer baskets, product
      families, exact input-list copies (47% copied, overlap unchanged) and locality settings
      did not move the mid bands. Next: measure how long the copied lists are, since short
      lists that agree by chance would explain the 39% without explaining the overlap.
- [ ] Run the six suites under pytest-codspeed: entry modules calling `bwbench.pytest.tests`,
      and a runner image (a spike ran traversal under CPU simulation; not in the repo yet).
- [ ] Check bw2data's write and Monte Carlo's first draw once per parameter set, not after
      every timed sample: each check loads matrices and runs a Neumann solve. Measure what
      that costs at the ecoinvent size first.
- [ ] `asv.sh` still names machines after the container hostname by default, which includes
      the host's name. `just results-commit` refuses such results; a neutral default
      (for example the slot name) would save a rerun.
- [ ] Setups solve once before the timed call (a warm-up and early check), on the same
      datapackage objects, so "first score" is warm. Time a cold `run()` on fresh packages
      against it in the box and decide whether to drop the warm-up at 25k products and up.
- [ ] Check that pytest-codspeed's `pedantic` calls the target once per setup under CPU
      simulation; a warm-up call would trip the seam's "run called twice" guard.
- [ ] Measure run-to-run noise (10 repeats of one commit) before publishing any number.
- [ ] Backfill each package on a pinned benchmark machine, in one fixed CPU slot, with
      `BWBENCH_SIZES=ecoinvent,exiobase`. Include the PyPardiso environments there.
- [ ] First publication: turn on GitHub Pages with "GitHub Actions" as the source, benchmark
      with a neutral `BWBENCH_MACHINE` (for example `pinned-e0`), then `just results-commit`,
      `git push origin results` and `gh workflow run site.yml`. Only after the noise is
      measured (above).
- [ ] Drop the `versions-*.txt` files once the pins check below has run: the lock files
      hold the same versions.
- [ ] The site job builds the box image and clones six upstream repos on every run, though
      `asv publish` only reads results. Run asv there directly, or cache `.asv/`, once the
      first runs show how long it takes. CodSpeed, if added, runs on `pull_request` only.
- [ ] Run `just registry-vs-sqlite ecoinvent` on the benchmark machine: does the SQLite path's 3e-8
      score error hold at size?

## Verify in the box

Checked on the benchmark machine on 2026-10-13: the read-only mount (plain docker only), `just smoke`,
the PyPardiso reset (4.32 ms against 3.18 ms at `cfad4bf`), the lock and the image tag.
Still open:

- [ ] Pins hold: run `just smoke` on another day and `diff` `.asv/smoke/*/smoke/versions-*.txt`
      against the copies in `.asv/versions-2026-10-13/`. Also check old releases in a full
      `just bench bw2calc`: a versions file showing another numpy means pip replaced the pin.
