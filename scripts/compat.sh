#!/bin/sh
# Do today's Brightway releases work together? Inside the box, or on a CI runner:
# scripts/compat.sh PYTHON
#
# Installs the latest PyPI releases of brightway25, bw_graph_tools and bw_timex into a fresh
# environment, with none of the cutoffs or stack pins the asv runs use. Then runs every
# benchmark once at smoke size through the pytest adapter in benchmarks/codspeed: each case
# runs and checks its result, and nothing is timed. The resolved set goes to
# .asv/compat/PYTHON/ (pylock.toml and freeze.txt) before the cases run, so a failing set is
# on record too.
set -eu
python=$1
out=.asv/compat/$python
venv=${TMPDIR:-/tmp}/compat-venv-$python
rm -rf "$out" "$venv"
mkdir -p "$out"
# in-box.sh holds releases back to its cutoff, and pyproject.toml's exclude-newer holds them
# back a week (--no-config). This column wants what a user installs today.
unset UV_EXCLUDE_NEWER PIP_UPLOADED_PRIOR_TO
printf '%s\n' brightway25 bw_graph_tools bw_timex pytest pytest-codspeed==5.0.3 |
    uv pip compile --quiet --no-config --no-header --python-version "$python" -o "$out/pylock.toml" -
uv venv --quiet --no-config --python "$python" "$venv"
uv pip install --quiet --no-config --python "$venv/bin/python" -r "$out/pylock.toml"
uv pip freeze --no-config --python "$venv/bin/python" >"$out/freeze.txt"
PYTHONPATH=benchmarks "$venv/bin/python" -m pytest -p no:cacheprovider --rootdir benchmarks/codspeed benchmarks/codspeed -v
