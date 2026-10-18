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
- [ ] A CodSpeed PR job (`CodSpeedHQ/action`, `pull_request` only) running `just codspeed`'s
      pytest command, once the repo has a CodSpeed token. All six suites
      pass under CPU simulation locally; counts repeat to within 0.02% with ASLR on.
- [ ] bw2calc 3.0.0 under PyPardiso costs about 380 M more instructions per new LCA object
      than 2.5.0 (`just codspeed bw2calc bw2calc==3.0.0 pypardiso`): each object's new
      `PyPardisoSolver()` searches the Python prefix for MKL with a recursive glob. Setting
      `PYPARDISO_MKL_RT` takes a smoke-size first score from 37 to 2.7 ms. Decide whether the
      box sets it (it would hide the cost users pay) or the history keeps showing it.
- [ ] `asv.sh` still names machines after the container hostname by default, which includes
      the host's name. `just results-commit` refuses such results; a neutral default
      (for example the slot name) would save a rerun.
- [ ] Rerun bw2data from `4.7~2` with more rounds (from 2026-10-19 after hours): from #268 on,
      a quarter of the database writes take over 26 s, against 15.4 to 15.5 s in 4.6.
- [ ] Check whether bw_graph_tools without PyPardiso factorizes once per calculation (9
      calculations take 4.6 minutes, about nine SuperLU factorizations). And why EXIOBASE
      with `max_calc` 2 and 100 counts 16 calculations in both, yet takes 11.3 s against
      2.25 minutes.
- [ ] bw_graph_tools 0.5 to 0.8 time out (900 s, warm-up included) on 6 of their 8 SuperLU
      cells and on EXIOBASE `max_calc=100` with PyPardiso. Decide: keep them as gaps, or raise
      the timeout for one night (about 7 hours of the slot).
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
