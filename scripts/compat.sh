#!/bin/sh
# Do today's Brightway releases work together? Inside the box, or on a CI runner:
# scripts/compat.sh PYTHON [latest|floors|pre]
#
# Installs PyPI releases of brightway25, bw_graph_tools and bw_timex into a fresh environment,
# with none of the cutoffs or stack pins the asv runs use. The column picks the releases:
#   latest  the newest release of everything (the default)
#   floors  the newest Brightway packages and test harness, with each package they depend on
#           directly at the lowest version their declared bounds allow that has a wheel, so a
#           lower bound set too low shows up
#   pre     like latest, but pre-releases count too (NumPy, SciPy and pandas betas)
# Then runs every benchmark once at smoke size through the pytest adapter in
# benchmarks/codspeed: each case runs and checks its result, and nothing is timed. A case the
# releases cannot run fails rather than skips, unless BWBENCH_STRICT is set empty (the macOS
# job: a solver its wheels lack is a platform gap, not a release problem). The resolved set
# goes to .asv/compat/PYTHON-COLUMN/requirements.txt, and as a PEP 751 lock (wheel URLs and
# hashes) to pylock.toml beside it, before the cases run, so a failing set is on record too.
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
    # brightway25, matrix_utils, stats_arrays, multifunctional, randonneur*, ecoinvent_interface,
    # mrio_common_metadata, dynamic_characterization), as uv names them.
    bw='bw2|bw-|brightway|matrix-utils|stats-arrays|multifunctional|randonneur|ecoinvent-interface|mrio-common-metadata|dynamic-characterization'
    # Pin those and the test harness at latest. Everything they depend on directly goes in
    # unpinned, so lowest-direct takes it to the floor their bounds allow. The rest gets the
    # newest version that fits, since a third-party package's own floors (python-dateutil's
    # six>=1.5, which predates Python 3.12) say nothing about Brightway.
    # Declared floors found too low on Python 3.12, raised so the run reaches the next one. Each
    # line is the oldest release that worked here (some only "worked", not bisected), with the
    # package that leaves it unbounded. Drop a line once that package's release raises it.
    cat >"$out/raised.txt" <<'EOF'
astunparse>=1.6.3      # bw2parameters (brightway2-parameters#15): 1.1.0 pulls six 1.6.1
pint>=0.18             # bw2parameters: 0.9 imports pkg_resources (not bisected)
fsspec>=2022.10.0      # bw_processing, bw2data, bw2calc: no dirfs before 2022.2, zip writes fail to 2022.8.2
structlog>=20.2.0      # bw2data: structlog.contextvars
voluptuous>=0.12.0     # bw2data: collections.Mapping in 0.11.5 (0.11.6 not tried)
xarray>=2023.1.0       # bw2calc: 0.7.0 imports collections.Mapping (not bisected)
threadpoolctl>=3.0.0   # bw2calc: ThreadpoolController
ipython>=8.0           # bw_timex: 7.x uses asyncio.coroutine (not bisected)
ipywidgets>=8.0        # bw_timex: collections.Mapping in 7.0 (not bisected)
seaborn>=0.13          # bw_timex: matplotlib.cm.register_cmap in 0.11 (0.12 not tried)
EOF
    # --no-build: only versions with a wheel for this Python, as a user's install would pick.
    awk -F ' *# via ' -v pin="^($bw|pytest)" -v via="(^|, )($bw)" '
        $1 ~ pin { print $1; next }
        $2 ~ via { sub(/==.*/, "", $1); print $1 }' "$out/latest.txt" |
        compile --no-annotate --resolution lowest-direct --no-build -c "$out/raised.txt" -o "$out/requirements.txt"
    ;;
esac
compile --no-annotate -o "$out/pylock.toml" <"$out/requirements.txt"
uv pip install --quiet --python "$py" -r "$out/requirements.txt"
BWBENCH_STRICT=${BWBENCH_STRICT-1} PYTHONPATH=benchmarks "$py" -m pytest -p no:cacheprovider --rootdir benchmarks/codspeed benchmarks/codspeed -v
