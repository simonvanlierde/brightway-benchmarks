# TODO

- [ ] Lower the `ecoinvent` profile's LU fill: COLAMD 323 and MMD_AT_PLUS_A 99 against
      ecoinvent's 175 and 76 (see the comment on `ECOINVENT` in `synth.py` for what was tried).
- [ ] Run the six suites under pytest-codspeed: entry modules calling `bwbench.pytest.tests`,
      and the runner image from the `spike/bench-seam` branch.
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
- [ ] matrix_utils #48: no release has it, so every commit times the same in both
      environments (about 720 ms at 1,000 groups on bw_processing 1.6, 420 ms with #113).
      Add a column for the #48 head from the fork to show its effect.
