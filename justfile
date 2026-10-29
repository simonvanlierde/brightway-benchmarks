# Task runner: https://just.systems. `just` lists the recipes, `just <name>` runs one.
#
# `import?` skips a recipe file you did not scaffold. Recipes are prefixed
# (`py-`, `ts-`, `rs-`, `go-`) because imports share one namespace, except the few only
# one kind has, such as `pipeline` or `up`.
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

# Fix and format every stack here, as each stack's `fmt` recipe does.
fmt:
    @just py-fmt

# Run every git hook over the whole repo, not just staged files.
hooks:
    prek run -a

# --- benchmarks --------------------------------------------------------------
# Everything below runs in the benchmark box, a throwaway `tmp-bwbench-*` container
# (docs/assurance-case.md). docs/running.md lists the BWBENCH_* variables.

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

# Today's PyPI releases of the Brightway set on PYTHON, then every case once at smoke size.
# COLUMN: latest, floors, pre, conda-forge or suites (docs/running.md, "Compat").
# 6g: every suite shares one pytest process here, not one process per case as under asv.
compat python="3.12" column="latest":
    BWBENCH_TARGET={{ if column == "conda-forge" { "conda" } else { "box" } }} BWBENCH_MEM=${BWBENCH_MEM:-6g} scripts/box.sh scripts/compat.sh {{ python }} {{ column }}

# Build the static history site in site/ from results/ (one asv site per subject plus an index).
# The index's compat table comes from the compat workflow's artifacts, read through `gh`.
site:
    #!/usr/bin/env bash
    set -euo pipefail
    for conf in asv/*.json; do
      s=$(basename "$conf" .json)
      if [ -d "results/$s" ]; then scripts/box.sh scripts/asv.sh "$s" publish; fi
    done
    scripts/compat_site.py site
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

# Protect the default branch (no deletion, no force-push, linear history, PRs squash-merged after the always-on checks pass and one approval) and the v* tags. Turn on private vulnerability reporting. Safe to rerun.
repo-settings:
    #!/usr/bin/env bash
    set -euo pipefail
    err=$(mktemp)
    trap 'rm -f "$err"' EXIT
    fail() {
        cat "$err" >&2
        grep -qE 'HTTP (403|404)' "$err" && echo "Rulesets on a private repo need a paid GitHub plan (or the repo does not exist, or you lack admin rights)." >&2
        exit 1
    }
    # Merge-method switches live on the repo itself; the ruleset also limits the PR button.
    gh api -X PATCH repos/{owner}/{repo} -F allow_squash_merge=true -F allow_merge_commit=false -F allow_rebase_merge=false >/dev/null 2>"$err" || fail
    # Each file's "name" matches its file name, so the recipe needs no jq to read it.
    for name in main main-checks tags; do
        file=.github/rulesets/$name.json
        id=$(gh api "repos/{owner}/{repo}/rulesets?includes_parents=false" --jq ".[] | select(.name == \"$name\") | .id" 2>"$err") || fail
        if [ -n "$id" ]; then
            gh api -X PUT "repos/{owner}/{repo}/rulesets/$id" --input "$file" >/dev/null 2>"$err" || fail
            echo "Updated ruleset '$name' ($id)."
        else
            gh api -X POST repos/{owner}/{repo}/rulesets --input "$file" >/dev/null 2>"$err" || fail
            echo "Created ruleset '$name'."
        fi
    done
    # SECURITY.md sends reports to a private security advisory, which this turns on.
    gh api -X PUT repos/{owner}/{repo}/private-vulnerability-reporting >/dev/null 2>"$err" || fail
    echo "Turned on private vulnerability reporting."

# Set the GitHub About box from your answers: description and a topic per stack. Adds topics, never removes yours. Safe to rerun.
repo-about:
    gh repo edit --description 'Continuous benchmarks for the Brightway LCA stack on seeded synthetic matrices' --add-topic python
