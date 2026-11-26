# This repository's own recipes, which copier updates never touch. The justfile imports this
# file, and `just check` ends with `local-check`.

# The viewer's checks, after the Python ones.
local-check: ui-check

# What the ui workflow runs before its browser tests. Fails when the generated types are stale.
ui-check:
    cd ui && pnpm install --frozen-lockfile
    cd ui && pnpm run types && git diff --exit-code src/lib
    cd ui && pnpm run check
    cd ui && pnpm run test
    cd ui && pnpm run build
    cd ui && pnpm run size
    cd ui && pnpm audit --prod --audit-level=moderate

# --- benchmarks --------------------------------------------------------------
# Everything below runs in the benchmark box, a throwaway `tmp-bwbench-*` container
# (docs/assurance-case.md). docs/running.md lists the BWBENCH_* variables.

# A rerun skips what already succeeded, so a backfill that stopped partway picks up where it
# was, if BWBENCH_MACHINE (or the CPU slot that names the machine, as box-e0) is the same.
# Extra arguments reach `asv run`, e.g. `just bench bw2calc "" -e` to show each check's message.
# Benchmark SUBJECT over its releases (asv/SUBJECT.hashes), or over RANGE (an asv range).
bench subject range="" *args:
    scripts/box.sh scripts/asv.sh {{ subject }} run --skip-existing-successful {{ args }} {{ if range == "" { "HASHFILE:/src/asv/" + subject + ".hashes" } else { quote(range) } }}

# After a generator version bump: only the newest release of each minor line (scripts/minor_lines.py).
bench-lines subject *args:
    mkdir -p .asv
    python3 scripts/minor_lines.py {{ subject }} > .asv/{{ subject }}.lines.hashes
    scripts/box.sh scripts/asv.sh {{ subject }} run --skip-existing-successful {{ args }} HASHFILE:/src/.asv/{{ subject }}.lines.hashes

# Proves the harness, not the numbers. Results go to .asv/smoke/, never to results/ or the site.
# One quick pass per subject at its oldest and latest release, smoke size, and a bw2io import of
# the smoke system written as ecoSpold2 files; fails on any failure.
smoke:
    #!/usr/bin/env bash
    set -uo pipefail
    status=0
    for conf in asv/*.json; do
      s=$(basename "$conf" .json)
      rm -rf ".asv/smoke/$s"
      for release in $( (head -n 1; tail -n 1) <"asv/$s.hashes" | uniq); do
        BWBENCH_MACHINE=smoke scripts/box.sh scripts/asv.sh "$s" run --quick --show-stderr "$release^!" || { echo "$s $release: exit $?"; status=1; }
      done
    done
    python3 scripts/check_smoke.py .asv/smoke || status=1
    # bw2io's import of the generated ecoSpold2 release, which must link every exchange.
    just bw2io-import synthetic smoke || { echo "bw2io-import: exit $?"; status=1; }
    exit $status

# Results go to .asv/noise/, never to results/ or the site. Sizes come from BWBENCH_* as usual.
# Short cases need the CPU's performance power profile (Linux: powerprofilesctl set performance).
# Each sample's CPU time, wall time and involuntary context switches go to rounds.jsonl beside them.
# Run-to-run noise: RUNS separate quick runs of SUBJECT's latest release, then each case's spread.
noise subject runs="10":
    #!/usr/bin/env bash
    set -uo pipefail
    last=$(tail -n 1 "asv/{{ subject }}.hashes")
    rm -rf ".asv/noise/{{ subject }}"
    for i in $(seq {{ runs }}); do
      echo "noise: run $i of {{ runs }}" >&2
      # A failed case fails the run, but the other cases' samples still count. asv's output goes
      # to stderr, so stdout carries only the summary below.
      BWBENCH_MACHINE=noise BWBENCH_ROUNDLOG="/src/.asv/noise/{{ subject }}/rounds.jsonl" scripts/box.sh scripts/asv.sh {{ subject }} run --quick --append-samples "$last^!" >&2 ||
        echo "noise: run $i exited $?" >&2
    done
    uv run --no-project --with numpy==2.5.3 python scripts/noise_summary.py ".asv/noise/{{ subject }}"

# Results go to .asv/ratios/box.json, which no history or site page reads (docs/running.md, "Hosted ratios").
# Interleaved ratios between environments at smoke size; COMPARISON as `bwbench compare` takes it.
ratios *comparisons:
    scripts/box.sh env PYTHONPATH=src python -m bwbench.compare compare {{ comparisons }} --work .asv/ratio-work -o .asv/ratios/box.json

# Results go to results/canary/BWBENCH_MACHINE/, which no Brightway history reads. The benchmark
# node runs it nightly, then `just results-commit` and `just canary-check`.
# The nightly canary: a fixed stdlib workload, so a move is the machine's (scripts/canary.py).
canary:
    scripts/box.sh python3 scripts/canary.py run "results/canary/${BWBENCH_MACHINE:?set BWBENCH_MACHINE to the results machine name}"

# Exits 1 when a workload moved beyond the earlier nights' noise. Runs on the host: it only reads JSON.
# The newest canary night against the ones before it, with fingerprint fields that changed.
canary-check:
    python3 scripts/canary.py check "results/canary/${BWBENCH_MACHINE:?set BWBENCH_MACHINE to the results machine name}"

# Runs on the host: it only compares files. The night queue runs it after the last job.
# Drop asv environments unused for DAYS days, then hardlink identical files across the rest.
tidy-envs days="30":
    python3 scripts/tidy_envs.py .asv/env --days {{ days }}

# After a new upstream release, follow docs/running.md ("Add a release").
# Resolve SUBJECT's fixed stack (its latest release's dependencies at the cutoff) into asv/.
stack subject:
    scripts/box.sh scripts/stack.sh {{ subject }}
    test ! -L ".asv/stack/{{ subject }}.txt"  # the box wrote it: never copy through a link
    cp ".asv/stack/{{ subject }}.txt" "asv/{{ subject }}.stack.txt"

# Results go to .asv/stack/. Failing cases are expected on old releases; the table is the signal.
# Every release of SUBJECT once at smoke size on its fixed stack, then which cases pass per release.
stack-check subject:
    rm -rf ".asv/stack/{{ subject }}"
    -BWBENCH_MACHINE=stack scripts/box.sh scripts/asv.sh {{ subject }} run --quick "HASHFILE:/src/asv/{{ subject }}.hashes"
    python3 scripts/release_report.py {{ subject }}

# Tags resolve through asv's clone of the upstream repository in .asv/SUBJECT, which `just bench` makes.
# Cases that moved beyond their noise between SUBJECT's newest two releases in results/, as Markdown.
release-changes subject:
    python3 scripts/release_changes.py {{ subject }} results

# Today's PyPI releases of the Brightway set on PYTHON, then every case once at smoke size.
# COLUMN: latest, floors, pre, conda-forge or suites (docs/running.md, "Compat").
# 6g: every suite shares one pytest process here, not one process per case as under asv.
compat python="3.13" column="latest":
    BWBENCH_TARGET={{ if column == "conda-forge" { "conda" } else { "box" } }} BWBENCH_MEM=${BWBENCH_MEM:-6g} scripts/box.sh scripts/compat.sh {{ python }} {{ column }}

# Build the static site in site/, around the viewer the site workflow adds: the compat archive (the
# `compat` branch, which the compat workflow writes) and redirects from the old asv pages. The
# `ratios` branch, which the ratios workflow writes, goes to build/ratios for `just ui-data`.
site:
    #!/usr/bin/env bash
    set -euo pipefail
    mkdir -p site
    [ ! -d profiles ] || { mkdir -p site/profiles && cp -r profiles/. site/profiles/; }
    # ls-remote exits 2 when a branch is missing, which is fine; any other failure stops the build,
    # so a network error cannot publish a site without its setup guidance or comparisons.
    status=0 && git ls-remote --quiet --exit-code origin refs/heads/compat >/dev/null || status=$?
    if [ "$status" = 0 ]; then git fetch --quiet origin compat && git archive FETCH_HEAD compat | tar -x -C site
    elif [ "$status" = 2 ]; then echo "no compat branch yet, so the site has no setup guidance" >&2
    else echo "could not reach origin for the compat branch (git ls-remote exit $status)" >&2 && exit 1
    fi
    rm -rf build/ratios && mkdir -p build/ratios
    status=0 && git ls-remote --quiet --exit-code origin refs/heads/ratios >/dev/null || status=$?
    if [ "$status" = 0 ]; then git fetch --quiet origin ratios && git archive FETCH_HEAD | tar -x -C build/ratios
    elif [ "$status" = 2 ]; then echo "no ratios branch yet, so the site has no comparisons across machines" >&2
    else echo "could not reach origin for the ratios branch (git ls-remote exit $status)" >&2 && exit 1
    fi
    for conf in asv/*.json; do
      s=$(basename "$conf" .json)
      # `just ui-data` reads release tags from asv's mirror; commits and tags are enough.
      repo=$(python3 scripts/asv_conf.py repo "$s")
      [ -d ".asv/$s" ] || git clone --quiet --bare --filter=tree:0 "$repo" ".asv/$s"
      # Old links into asv's pages: SUBJECT/index.html#NAME opens NAME's history in the viewer.
      mkdir -p "site/$s"
      printf '%s\n' '<!doctype html><meta charset="utf-8"><title>Moved</title>' \
        "<script>location.replace('../?page=explorer&group=$s'+(location.hash.length>1?'&bench='+encodeURIComponent(location.hash.slice(1).split('?')[0]):''))</script>" \
        '<p>The benchmark histories have moved to <a href="../?page=explorer">the explorer</a>.</p>' >"site/$s/index.html"
    done
    # The old landing page's anchors (#works-together, #latest-release) still mean something to the viewer.
    printf '%s\n' '<!doctype html><meta charset="utf-8"><title>Moved</title>' \
      "<script>location.replace(location.hash ? './' + location.hash : './?page=explorer')</script>" \
      '<p>The benchmark histories have moved to <a href="./?page=explorer">the explorer</a>.</p>' >site/asv.html

# Build the viewer and serve it on 127.0.0.1:PORT with the committed real data, to look at a UI
# change (a PR checked out with `gh pr checkout`). From a laptop: ssh -L PORT:localhost:PORT HOST.
ui-serve port="4400":
    # A local look only, so the host's pnpm may stand in for the pinned one (CI uses the pin).
    cd ui && export npm_config_manage_package_manager_versions=false && pnpm install --frozen-lockfile && pnpm run build && node e2e/serve.mjs {{ port }}

# Write the UI's data from results/ to OUT (scripts/export_ui.py says what it reads), and the setup
# guidance from site/compat/status.json, which `just site` fetches; without it there is none. The
# Python support table comes from site/compat/python-probe.json (scripts/probe_site.py); without it there is none.
# The comparisons across machines come from build/ratios (`just site`) and ratios/contributed. Their validator runs
# with uv.lock's packages only, without building the project: its build backend is not in the lock.
# Needs uv: change points come from Apache Otava, in an environment of its own.
ui-data out:
    python3 scripts/export_ui.py results {{ out }}
    python3 scripts/export_guidance.py site/compat/status.json {{ out }} --probe site/compat/python-probe.json
    uv sync --frozen --no-install-project
    PYTHONPATH=src uv run --no-sync python scripts/export_ratios.py build/ratios ratios/contributed {{ out }}

# Commit results/ to the local `results` branch for the site; refuses results that name this host.
results-commit:
    scripts/results-commit.sh

# bw2calc's own lci() with one sparse solver: superlu, umfpack, pypardiso, umfpack-T or klu.
# 12 GB by default on plain docker: SuperLU on A at the ecoinvent size needs several.
solver-lci solver size="smoke" bw2calc="3.1.0":
    BWBENCH_MEM="${BWBENCH_MEM:-12g}" scripts/box.sh sh -c 'PYTHONPATH=src uv run -q --no-project --python 3.13 --with bw2calc=={{ bw2calc }} --with threadpoolctl==3.7.0 --with pypardiso==0.4.7 --with scikit-umfpack==0.4.2 --with pyklu==0.2.0 python scripts/solver_lci.py {{ solver }} {{ size }}'

# Every generated profile, or the PROFILES given, goes to .asv/dataset-v<GENERATOR_VERSION>/
# (docs/running.md#publish-the-synthetic-inputs). 12 GB of memory by default and about 34 GB of disk
# in .asv/ for `regional` (250k products); name smaller profiles to skip it.
# The synthetic inputs as a Zenodo dataset: matrices, ecoSpold2 files, card and checksums. Uploads nothing.
dataset *profiles:
    #!/usr/bin/env bash
    set -euo pipefail
    v=$(sed -n 's/^GENERATOR_VERSION = "\(.*\)"$/\1/p' src/bwbench/synth.py)
    [ -n "$v" ] || { echo "no GENERATOR_VERSION in src/bwbench/synth.py" >&2; exit 1; }
    BWBENCH_MEM="${BWBENCH_MEM:-12g}" exec scripts/box.sh sh -c "PYTHONPATH=src uv run -q --no-project --python 3.13 --with numpy==2.5.3 --with scipy==1.18.1 --with bw_processing==1.6 python scripts/dataset.py .asv/dataset-v$v {{ profiles }}"

# RELEASE: a licensed release folder (holding datasets/ and MasterData/), mounted read-only, with
# dataset counts or `all` as SIZES (3000,all); or `synthetic`, with profiles as SIZES (smoke,ecoinvent).
# 8 GB by default: a full import peaks at about 4.5 GB.
# Time and peak memory of an ecoinvent import with bw2io 0.9.17 and bw2data 4.8, a fresh process per size.
bw2io-import release sizes:
    #!/usr/bin/env bash
    set -euo pipefail
    run='PYTHONPATH=src uv run -q --no-project --python 3.13 --with bw2io==0.9.17 --with bw2data==4.8 python scripts/bw2io_import.py'
    export BWBENCH_MEM="${BWBENCH_MEM:-8g}"
    if [ {{ quote(release) }} = synthetic ]; then
      exec scripts/box.sh sh -c "$run synthetic {{ quote(sizes) }}"
    fi
    # box.sh mounts only this repo, so a licensed release needs a plain docker run of its image.
    image=$(scripts/box.sh --image)
    exec docker run --rm -i --init --name "tmp-bwbench-$$" --user "$(id -u):$(id -g)" --cap-drop ALL \
      --security-opt no-new-privileges --pids-limit 4096 --memory "$BWBENCH_MEM" --memory-swap "$BWBENCH_MEM" \
      --cpus "${BWBENCH_CPUS:-2}" \
      -v "$PWD":/src:ro -v "$PWD/.asv":/src/.asv -v "$(realpath {{ quote(release) }})":/ecoinvent:ro -w /src \
      "$image" scripts/in-box.sh sh -c "$run /ecoinvent {{ quote(sizes) }}"

# Docker's default seccomp profile (moby/profiles at TAG; v0.2.4 is Docker 29.9's) plus one rule
# allowing personality(ADDR_NO_RANDOMIZE), so `setarch -R` can turn address randomization off.
# Rewrite docker/seccomp-noaslr.json, the profile box.sh gives the codspeed box.
seccomp-profile tag="seccomp/v0.2.4":
    curl -fsSL "https://raw.githubusercontent.com/moby/profiles/{{ tag }}/seccomp/default.json" | jq '.syscalls = [{"names": ["personality"], "action": "SCMP_ACT_ALLOW", "args": [{"index": 0, "value": 262144, "op": "SCMP_CMP_EQ"}]}] + .syscalls' >docker/seccomp-noaslr.json

# CodSpeed counts instructions, not seconds, so a busy machine changes nothing. Profiles go to
# .asv/codspeed/SUBJECT/; nothing is uploaded. Smoke size unless BWBENCH_SIZES says otherwise.
# One suite under pytest-codspeed's CPU simulation; extra packages (a solver) come on top.
codspeed subject *packages:
    BWBENCH_TARGET=codspeed BWBENCH_SIZES="${BWBENCH_SIZES:-smoke}" scripts/box.sh scripts/codspeed.sh {{ subject }} {{ packages }}

# Profile one case under pyinstrument, as `just profile bw2calc first_score release=3.0.0
# with=scikit-umfpack size=ecoinvent cls=IterativeLCA`: release= and with= pick the environment
# (the latest release, and bw2calc's SuperLU, when left out), NAME=VALUE the parameters. HTML and speedscope
# JSON go to .asv/profiles/.
profile subject case *args:
    scripts/box.sh scripts/profile.sh {{ subject }} {{ case }} {{ args }}
