# TODO

- [ ] Decide the generator's structure before calibrating. Random input rows fill SuperLU's
      L+U to about 60% of a dense matrix (27.95 s at 8,000 products), so sizes from
      `ecoinvent` up time that fill. Then calibrate `SIZES` against public summary statistics.
- [ ] Measure run-to-run noise (10 repeats of one commit) before publishing any number.
- [ ] Backfill each package on the devbox in one `oss-bench` slot, with
      `BWBENCH_SIZES=ecoinvent,exiobase`. Include the PyPardiso environments there.
- [ ] Publish the site from a gh-pages branch. The benchmark job gets `contents: read` and
      a separate job deploys; no self-hosted runner. CodSpeed, if added, runs on
      `pull_request` only.
- [ ] Run `just registry-vs-sqlite ecoinvent` on the devbox: does the SQLite path's 3e-8
      score error hold at size?
- [ ] `oss-bench` mounts the repo read-write. Add a read-only mode there, as `box.sh` has.

## Verify in the box

Run on the devbox on 2026-10-13: the read-only mount (plain docker; see the oss-bench item
above), `just smoke`, the PyPardiso reset (4.32 ms against 3.18 ms at `cfad4bf`), the lock
and the image tag all behave as intended. Open:

- [ ] Pins hold: run `just smoke` on another day and `diff` `.asv/smoke/*/smoke/versions-*.txt`
      against the copies in `.asv/versions-2026-10-13/`. Also check old releases in a full
      `just bench bw2calc`: a versions file showing another numpy means pip replaced the pin.
- [ ] matrix_utils: the #113 environment holds bw_processing 1.6 from PyPI, not the fork at
      `1a6f898`, so both environments time the same. Make the `git+` requirement stick, then
      check that 0.8 and 0.9 differ in the #113 environment.
- [ ] Traversal: at smoke size the cutoff ends `max_calc=100` after 6 nodes, so that case does
      not test `max_calc`. Pick a size or cutoff where it binds.
- [ ] CI: run `gh workflow run smoke.yml`. It should go green, and red with one check flipped
      on a branch.
