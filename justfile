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

# Benchmark SUBJECT over its releases (asv/SUBJECT.hashes), or over RANGE (an asv range).
# Extra arguments reach `asv run`, e.g. `just bench bw2calc "" -e` to show each check's message.
bench subject range="" *args:
    scripts/box.sh scripts/asv.sh {{ subject }} run {{ args }} {{ if range == "" { "HASHFILE:/src/asv/" + subject + ".hashes" } else { quote(range) } }}

# One quick pass per subject at its latest release, smoke size: proves the harness, not the numbers.
# Results go to .asv/smoke/, never to results/ or the site. Fails on any failed benchmark.
smoke:
    #!/usr/bin/env bash
    set -uo pipefail
    status=0
    for conf in asv/*.json; do
      s=$(basename "$conf" .json)
      last=$(tail -n 1 "asv/$s.hashes")
      rm -rf ".asv/smoke/$s"
      BWBENCH_MACHINE=smoke scripts/box.sh scripts/asv.sh "$s" run --quick --show-stderr "$last^!" || { echo "$s: exit $?"; status=1; }
    done
    python3 scripts/check_smoke.py .asv/smoke || status=1
    exit $status

# Build the static history site in site/ from results/ (one asv site per subject plus an index).
site:
    #!/usr/bin/env bash
    set -euo pipefail
    for conf in asv/*.json; do
      s=$(basename "$conf" .json)
      if [ -d "results/$s" ]; then scripts/box.sh scripts/asv.sh "$s" publish; fi
    done
    scripts/site_index.py site

# bw2data #290: SQLite project against sentier-brightway's Parquet registry. size: smoke | ecoinvent.
registry-vs-sqlite size="smoke":
    scripts/box.sh sh -c 'PYTHONPATH=src uv run -q --no-project --python 3.12 --with "sentier-brightway @ git+https://github.com/sentier-dev/sentier-brightway@adacaf9" --with bw2data --with bw2calc python scripts/registry_vs_sqlite.py {{ size }}'
