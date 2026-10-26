#!/bin/sh
# Do today's Brightway releases work together? Inside the box, or on a CI runner:
# scripts/compat.sh PYTHON
#
# Installs the latest PyPI releases of brightway25, bw_graph_tools and bw_timex into a fresh
# environment, with none of the cutoffs or stack pins the asv runs use. Then runs every
# benchmark once at smoke size through the pytest adapter in benchmarks/codspeed: each case
# runs and checks its result, and nothing is timed. A case the releases cannot run fails
# rather than skips. The resolved set goes to .asv/compat/PYTHON/requirements.txt before the
# cases run, so a failing set is on record too.
set -eu
python=$1
out=.asv/compat/$python
venv=${TMPDIR:-/tmp}/compat-venv-$python
rm -rf "$out" "$venv"
mkdir -p "$out"
# in-box.sh holds releases back to its cutoff, and pyproject.toml's exclude-newer holds them
# back a week. This column wants what a user installs today.
unset UV_EXCLUDE_NEWER PIP_UPLOADED_PRIOR_TO
export UV_NO_CONFIG=1
# Smoke sizes and the default solver, whatever the calling shell exports.
unset BWBENCH_SIZES BWBENCH_MC_SIZES BWBENCH_TIMEX_SIZES BWBENCH_WRITE_SIZES BWBENCH_SOLVER BWBENCH_SOLVERS
uv venv --quiet --python "$python" "$venv"
printf '%s\n' brightway25 bw_graph_tools bw_timex pytest pytest-codspeed==5.0.3 |
    uv pip compile --quiet --no-header --no-annotate --python "$venv/bin/python" -o "$out/requirements.txt" -
uv pip install --quiet --python "$venv/bin/python" -r "$out/requirements.txt"
BWBENCH_STRICT=1 PYTHONPATH=benchmarks "$venv/bin/python" -m pytest -p no:cacheprovider --rootdir benchmarks/codspeed benchmarks/codspeed -v
