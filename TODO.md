# TODO

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
      The gap is not one seed's: over 8 seeds COLAMD fill is 342 +- 15 and MMD 98 +- 3 (A^T:
      86 +- 4 and 25 +- 1, against ecoinvent's 26 and 17), and the overlap without hubs
      0.882 +- 0.005 over 64 seeds. Seed 0 sits within 1.3 SD of the mean on every one.
- [ ] A CodSpeed PR job (`CodSpeedHQ/action`, `pull_request` only) running `just codspeed`'s
      pytest command, once the repo has a CodSpeed token. All six suites
      pass under CPU simulation locally; counts repeat to within 0.02% with ASLR on.
- [ ] bw2calc 3.0.0 under PyPardiso costs about 380 M more instructions per new LCA object
      than 2.5.0 (`just codspeed bw2calc bw2calc==3.0.0 pypardiso`): each object's new
      `PyPardisoSolver()` searches the Python prefix for MKL with a recursive glob. Setting
      `PYPARDISO_MKL_RT` takes a smoke-size first score from 37 to 2.7 ms. Decide whether the
      box sets it (it would hide the cost users pay) or the history keeps showing it.
      Still there in 3.1.0 by wall time (2026-10-19). A fix that caches the lookup in
      pypardiso itself is ready to propose upstream; if it is released, the history shows it
      only once the fixed stack moves to that pypardiso.
- [ ] Drop the PyPI subjects' `versions-*.txt` files once the pins check below has run: the
      lock files hold the same versions. Keep them for `bw2calc-conda`, which has no lock file
      and records each conda package's build there.
- [ ] The site job builds the box image and clones six upstream repos on every run, though
      `asv publish` only reads results. Run asv there directly, or cache `.asv/`, once the
      first runs show how long it takes. CodSpeed, if added, runs on `pull_request` only.

## Verify in the box

Checked on the benchmark machine on 2026-10-13: the read-only mount (plain docker, and oss-bench through `OSS_BENCH_RW`), `just smoke`,
the PyPardiso reset (4.32 ms against 3.18 ms at `cfad4bf`), the lock and the image tag.
Still open:

- [ ] Pins hold: run `just smoke` on another day and `diff` `.asv/smoke/*/smoke/versions-*.txt`
      against the copies in `.asv/versions-2026-10-13/`. Also check old releases in a full
      `just bench bw2calc`: a versions file showing another numpy means pip replaced the pin.
