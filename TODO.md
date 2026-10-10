# TODO

- [ ] Run the full release backfill per package on the devbox, in one pinned `oss-bench`
      slot, with `BWBENCH_SIZES=ecoinvent,exiobase` and `BWBENCH_MACHINE` set per slot.
- [ ] Measure run-to-run noise (10 repeats of one commit) before publishing any number.
- [ ] Add PyPardiso environments on x86_64 (`BWBENCH_SOLVERS=pypardiso,umfpack`).
- [ ] Decide where `results/` and `site/` live (gh-pages branch or committed) and add the
      Pages workflow with one weekly scheduled run (plan M1).
- [ ] Calibrate `SIZES` inputs and flows against public summary statistics.
- [ ] Run `just registry-vs-sqlite ecoinvent` on the devbox and check whether the SQLite
      path's 3e-8 score difference against float64 holds at size.
- [ ] Combined bw_processing #113 + matrix_utils #48 column: install the #113 head in the
      matrix_utils environment.
