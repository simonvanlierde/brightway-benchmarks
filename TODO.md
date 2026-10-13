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

None of these has run yet.

- [ ] Read-only mount: `scripts/box.sh sh -c 'touch /src/justfile'` fails, and
      `scripts/box.sh sh -c 'touch /src/.asv/x && rm /src/.asv/x'` works.
- [ ] `just smoke` passes. If `IterativeLCA` fails in `NewDemand` or `MonteCarlo`, read the
      stderr: bw2calc 2.5.0 passes `atol="legacy"` to scipy's `cgs`, which scipy 1.18
      may reject. If confirmed, report it upstream.
- [ ] Pins hold: copy `.asv/smoke/*/smoke/versions-*.txt` aside, run `just smoke` on
      another day, and `diff` the two sets. Also check old releases in a full
      `just bench bw2calc`: a versions file showing another numpy means pip replaced the pin.
- [ ] PyPardiso reset, on the devbox (x86_64): run
      `BWBENCH_SOLVERS=pypardiso just bench bw2calc "2.5.0^!"` here and in a worktree at
      `cfad4bf`. `time_first_score` should be higher here.
- [ ] matrix_utils: `just bench matrix_utils` builds a bw_processing 1.6 and a #113
      environment. In the #113 one, 0.8 and 0.9 should differ.
- [ ] Traversal: `just bench bw_graph_tools "0.10^!" -e` and compare
      `track_calculation_count` for `max_calc` 2 and 100.
- [ ] Lock: start `just bench bw2calc "2.5.0^!"` twice at once. The second exits at once
      with "another bw2calc run holds".
- [ ] Image tag: edit a comment in `docker/Dockerfile`; the next `just smoke` prints
      "building the box image".
- [ ] CI: after merging, run `gh workflow run smoke.yml`. It should go green, and red
      with one check flipped on a branch.
