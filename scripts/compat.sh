#!/bin/sh
# Do today's Brightway releases work together? Inside the box, or on a CI runner:
# scripts/compat.sh PYTHON [latest|floors|pre]
#
# Installs PyPI releases of brightway25, bw_graph_tools and bw_timex into a fresh environment,
# with none of the cutoffs or stack pins the asv runs use. The column picks the releases:
#   latest  the newest release of everything (the default)
#   floors  the newest Brightway packages, with each package they depend on at the lowest
#           version their declared bounds allow, so a lower bound set too low shows up
#   pre     like latest, but pre-releases count too (NumPy, SciPy and pandas betas)
# Then runs every benchmark once at smoke size through the pytest adapter in
# benchmarks/codspeed: each case runs and checks its result, and nothing is timed. A case the
# releases cannot run fails rather than skips. The resolved set goes to
# .asv/compat/PYTHON-COLUMN/requirements.txt before the cases run, so a failing set is on
# record too.
set -eu
python=$1
column=${2:-latest}
case $column in
latest | floors | pre) ;;
*)
    echo "usage: scripts/compat.sh PYTHON [latest|floors|pre]" >&2
    exit 2
    ;;
esac
out=.asv/compat/$python-$column
venv=${TMPDIR:-/tmp}/compat-venv-$python-$column
rm -rf "$out" "$venv"
mkdir -p "$out"
# in-box.sh holds releases back to its cutoff, and pyproject.toml's exclude-newer holds them
# back a week. This column wants what a user installs today.
unset UV_EXCLUDE_NEWER PIP_UPLOADED_PRIOR_TO
export UV_NO_CONFIG=1
# Smoke sizes and the default solver, whatever the calling shell exports.
unset BWBENCH_SIZES BWBENCH_MC_SIZES BWBENCH_TIMEX_SIZES BWBENCH_WRITE_SIZES BWBENCH_SOLVER BWBENCH_SOLVERS
uv venv --quiet --python "$python" "$venv"
py=$venv/bin/python
[ -e "$py" ] || py=$venv/Scripts/python.exe # a Windows venv
reqs() { printf '%s\n' brightway25 bw_graph_tools bw_timex pytest pytest-codspeed==5.0.3; }
compile() { uv pip compile --quiet --no-header --python "$py" "$@" -; }
case $column in
latest) reqs | compile --no-annotate -o "$out/requirements.txt" ;;
pre) reqs | compile --no-annotate --prerelease allow -o "$out/requirements.txt" ;;
floors)
    reqs | compile --annotation-style line -o "$out/latest.txt"
    # The packages the Brightway project publishes (the brightway-lca GitHub org: bw2*, bw_*,
    # brightway25, matrix_utils, stats_arrays, multifunctional, randonneur*), as uv names them.
    bw='bw2|bw-|brightway|matrix-utils|stats-arrays|multifunctional|randonneur'
    # Pin those and the test harness at latest. Everything they depend on directly goes in
    # unpinned, so lowest-direct takes it to the floor their bounds allow. The rest gets the
    # newest version that fits, since a third-party package's own floors (python-dateutil's
    # six>=1.5, which predates Python 3.12) say nothing about Brightway.
    # --no-build: only versions with a wheel for this Python, as a user's install would pick.
    {
        reqs
        awk -F ' *# via ' -v pin="^($bw|pytest)" -v via="(^|, )($bw)" '
            $1 ~ pin { print $1; next }
            $2 ~ via { sub(/==.*/, "", $1); print $1 }' "$out/latest.txt"
    } | compile --no-annotate --resolution lowest-direct --no-build -o "$out/requirements.txt"
    ;;
esac
uv pip install --quiet --python "$py" -r "$out/requirements.txt"
BWBENCH_STRICT=1 PYTHONPATH=benchmarks "$py" -m pytest -p no:cacheprovider --rootdir benchmarks/codspeed benchmarks/codspeed -v
