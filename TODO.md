# TODO

- [ ] Lower the `ecoinvent` profile's LU fill: COLAMD 323 and MMD_AT_PLUS_A 99, against
      ecoinvent's 175 and 76. The comment on `ECOINVENT` in `synth.py` lists what was tried.
- [ ] Run the six suites under pytest-codspeed: entry modules calling `bwbench.pytest.tests`,
      and the runner image from the `spike/bench-seam` branch.
- [ ] Check bw2data's write and Monte Carlo's first draw once per parameter set, not after
      every timed sample: each check loads matrices and runs a Neumann solve. Measure what
      that costs at the ecoinvent size first.
- [ ] Before publishing results, require a neutral `BWBENCH_MACHINE` in `asv.sh`: asv names
      each machine folder after the container hostname, which includes the host's name.
- [ ] Setups solve once before the timed call (a warm-up and early check), on the same
      datapackage objects, so "first score" is warm. Time a cold `run()` on fresh packages
      against it in the box and decide whether to drop the warm-up at 25k products and up.
- [ ] Check that pytest-codspeed's `pedantic` calls the target once per setup under CPU
      simulation; a warm-up call would trip the seam's "run called twice" guard.
- [ ] Measure run-to-run noise (10 repeats of one commit) before publishing any number.
- [ ] Backfill each package on the devbox in one `oss-bench` slot, with
      `BWBENCH_SIZES=ecoinvent,exiobase`. Include the PyPardiso environments there.
- [ ] Keep results as data on a `results` branch (asv JSON, lock files, RO-Crate per machine)
      and build the site from it in CI, instead of from a local `results/`.
- [ ] Drop the `versions-*.txt` files once the pins check below has run: the lock files
      hold the same versions.
- [ ] Publish the site from a gh-pages branch. The benchmark job gets `contents: read` and
      a separate job deploys; no self-hosted runner. CodSpeed, if added, runs on
      `pull_request` only.
- [ ] Run `just registry-vs-sqlite ecoinvent` on the devbox: does the SQLite path's 3e-8
      score error hold at size?
- [ ] `oss-bench` mounts the repo read-write. Add a read-only mode there, as `box.sh` has.

## Verify in the box

Checked on the devbox on 2026-10-13: the read-only mount (plain docker only), `just smoke`,
the PyPardiso reset (4.32 ms against 3.18 ms at `cfad4bf`), the lock and the image tag.
Still open:

- [ ] Pins hold: run `just smoke` on another day and `diff` `.asv/smoke/*/smoke/versions-*.txt`
      against the copies in `.asv/versions-2026-10-13/`. Also check old releases in a full
      `just bench bw2calc`: a versions file showing another numpy means pip replaced the pin.
- [ ] matrix_utils #48: no release has it, so every commit times the same in both
      environments (about 720 ms at 1,000 groups on bw_processing 1.6, 420 ms with #113).
      Add a column for the #48 head from the fork to show its effect.
