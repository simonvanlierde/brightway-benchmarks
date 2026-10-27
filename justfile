# Task runner: https://just.systems. `just` lists the recipes, `just <name>` runs one.
#
# `import?` skips a recipe file you did not scaffold. Recipes are prefixed
# (`py-`, `ts-`, `rs-`, `go-`) because imports share one namespace.
import? 'just/python.just'
import? 'just/ts.just'
import? 'just/rust.just'
import? 'just/go.just'
import? 'just/docker.just'

# List the recipes (what a bare `just` runs).
default:
    @just --list

# The stack checks CI runs. `just hooks` runs the git hooks, which CI also runs.
check:
    @just py-check

# Run every git hook over the whole repo, not just staged files.
hooks:
    prek run -a

# --- benchmarks --------------------------------------------------------------
# Everything below runs in a throwaway `tmp-bwbench-*` container (scripts/box.sh):
# Brightway's code never runs on the host. BWBENCH_* variables set sizes and labels.

# A rerun skips what already succeeded, so a backfill that stopped partway picks up where it
# was, if BWBENCH_MACHINE (or the CPU slot that names the machine, as box-e0) is the same.
# Extra arguments reach `asv run`, e.g. `just bench bw2calc "" -e` to show each check's message.
# Benchmark SUBJECT over its releases (asv/SUBJECT.hashes), or over RANGE (an asv range).
bench subject range="" *args:
    scripts/box.sh scripts/asv.sh {{ subject }} run --skip-existing-successful {{ args }} {{ if range == "" { "HASHFILE:/src/asv/" + subject + ".hashes" } else { quote(range) } }}

# Proves the harness, not the numbers. Results go to .asv/smoke/, never to results/ or the site.
# One quick pass per subject at its oldest and latest release, smoke size; fails on any failure.
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

# After a new upstream release: add it to asv/SUBJECT.hashes, move the cutoff in scripts/in-box.sh,
# run `just stack SUBJECT`, then `just stack-check SUBJECT` and drop the releases that no longer run.
# Resolve SUBJECT's fixed stack (its latest release's dependencies at the cutoff) into asv/.
stack subject:
    scripts/box.sh scripts/stack.sh {{ subject }}
    cp ".asv/stack/{{ subject }}.txt" "asv/{{ subject }}.stack.txt"

# Results go to .asv/stack/. Failing cases are expected on old releases; the table is the signal.
# Every release of SUBJECT once at smoke size on its fixed stack, then which cases pass per release.
stack-check subject:
    rm -rf ".asv/stack/{{ subject }}"
    -BWBENCH_MACHINE=stack scripts/box.sh scripts/asv.sh {{ subject }} run --quick "HASHFILE:/src/asv/{{ subject }}.hashes"
    python3 scripts/release_report.py {{ subject }}

# Today's PyPI releases of the Brightway set on PYTHON, then every case once at smoke size.
# COLUMN: latest, floors or pre (see scripts/compat.sh).
# 6g: every suite shares one pytest process here, not one process per case as under asv.
compat python="3.12" column="latest":
    BWBENCH_MEM=${BWBENCH_MEM:-6g} scripts/box.sh scripts/compat.sh {{ python }} {{ column }}

# Build the static history site in site/ from results/ (one asv site per subject plus an index).
site:
    #!/usr/bin/env bash
    set -euo pipefail
    for conf in asv/*.json; do
      s=$(basename "$conf" .json)
      if [ -d "results/$s" ]; then scripts/box.sh scripts/asv.sh "$s" publish; fi
    done
    scripts/site_index.py site

# Commit results/ to the local `results` branch for the site; refuses results that name this host.
results-commit:
    scripts/results-commit.sh

# bw2calc's own lci() with one sparse solver: superlu, umfpack, pypardiso, umfpack-T or klu.
# 12 GB by default on plain docker: SuperLU on A at the ecoinvent size needs several.
solver-lci solver size="smoke" bw2calc="3.1.0":
    BWBENCH_MEM="${BWBENCH_MEM:-12g}" scripts/box.sh sh -c 'PYTHONPATH=src uv run -q --no-project --python 3.12 --with bw2calc=={{ bw2calc }} --with threadpoolctl==3.7.0 --with pypardiso==0.4.7 --with scikit-umfpack==0.4.2 --with pyklu==0.2.0 python scripts/solver_lci.py {{ solver }} {{ size }}'

# A SQLite project against sentier-brightway's Parquet registry (the format of bw2data #290, which
# stays outside bw2data). size: smoke | ecoinvent; solver: superlu | pypardiso.
registry-vs-sqlite size="smoke" solver="superlu":
    scripts/box.sh sh -c 'PYTHONPATH=src uv run -q --no-project --python 3.12 --with "sentier-brightway @ git+https://github.com/sentier-dev/sentier-brightway@adacaf9" --with bw2data==4.8 --with bw2calc==3.1.0 --with threadpoolctl==3.7.0 {{ if solver == "pypardiso" { "--with pypardiso==0.4.7" } else if solver == "superlu" { "" } else { error("solver: superlu or pypardiso") } }} --with duckdb==1.5.6 python scripts/registry_vs_sqlite.py {{ size }}'

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
