#!/bin/sh
# Do today's Brightway releases work together? Inside the box, or on a CI runner:
# scripts/compat.sh PYTHON [latest|floors|pre|conda-forge|suites]
#
# docs/running.md ("Compat") says what each column installs and what a run writes. The
# resolved set goes to .asv/compat/PYTHON-COLUMN/ before the cases run, so a failing set is on
# record too.
set -eu
python=$1
column=${2:-latest}
case $column in
latest | floors | pre | conda-forge | suites) ;;
*)
    echo "usage: scripts/compat.sh PYTHON [latest|floors|pre|conda-forge|suites]" >&2
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
if [ "$column" = conda-forge ]; then
    # brightway25's Brightway dependencies that conda-forge has, PyPardiso as bw_timex brings it
    # on Linux, and the test harness. Add a package here once it lands on conda-forge.
    mkdir -p "$venv"
    cat >"$venv/pixi.toml" <<EOF
[workspace]
name = "bwbench-compat"
channels = ["conda-forge"]
platforms = ["linux-64"]

[dependencies]
python = "$python.*"
bw2analyzer = "*"
bw2calc = "*"
bw2data = "*"
bw2io = "*"
bw2parameters = "*"
bw_migrations = "*"
bw_processing = "*"
ecoinvent_interface = "*"
matrix_utils = "*"
mrio_common_metadata = "*"
randonneur = "*"
randonneur_data = "*"
stats_arrays = "*"
pypardiso = "*"
pytest = "*"
pytest-codspeed = "==5.0.3"
EOF
    pixi lock --quiet --no-config --manifest-path "$venv/pixi.toml"
    cp "$venv/pixi.toml" "$venv/pixi.lock" "$out/"
    pixi install --quiet --no-config --frozen --manifest-path "$venv/pixi.toml"
    py=$venv/.pixi/envs/default/bin/python
    # The Python packages in the set, named as uv names them, for the job summary and the site.
    "$py" -c 'import importlib.metadata as m, re
print("\n".join(sorted({re.sub("[-_.]+", "-", d.name).lower() + "==" + d.version for d in m.distributions()})))' \
        >"$out/requirements.txt"
    # The suites whose package conda-forge lacks (as are brightway25, bw_simapro_csv and
    # multifunctional). Drop a name once it lands there.
    set --
    for suite in bw_graph_tools bw_timex; do
        echo "compat.sh: $suite is not on conda-forge, its cases are left out" >&2
        set -- "$@" "--ignore=benchmarks/codspeed/test_$suite.py"
    done
    exec env BWBENCH_STRICT="${BWBENCH_STRICT-1}" PYTHONPATH=benchmarks "$py" -m pytest -p no:cacheprovider \
        --rootdir benchmarks/codspeed benchmarks/codspeed "$@" -v
fi
uv venv --quiet --python "$python" "$venv"
py=$venv/bin/python
[ -e "$py" ] || py=$venv/Scripts/python.exe # a Windows venv
reqs() { printf '%s\n' brightway25 bw_graph_tools bw_timex pytest pytest-codspeed==5.0.3; }
# What the packages' `testing` extras add, less the coverage tools, which these runs leave off.
testreqs() { reqs && printf '%s\n' bw_temporalis pytest-mock pyarrow fsspec setuptools packaging; }
compile() { uv pip compile --quiet --no-header --python "$py" "$@" -; }
case $column in
latest) reqs | compile --no-annotate -o "$out/requirements.txt" ;;
suites) testreqs | compile --no-annotate -o "$out/requirements.txt" ;;
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
    # line is the oldest release that passes, bisected against this column or the package's own
    # tests, with the package that leaves it unbounded. Drop a line once that release raises it.
    cat >"$out/raised.txt" <<'EOF'
astunparse>=1.6.3      # bw2parameters (brightway2-parameters#15): 1.1.0 pulls six 1.6.1
asteval>=0.9.27        # bw2parameters: eval(raise_errors=) from 0.9.24, which has no 3.12 wheel until 0.9.27
pint>=0.18             # bw2data: 0.17 lacks pint.util._subs_re_list, 0.14 imports pkg_resources
fsspec>=2023.3.0       # bw_processing: zip compression is ignored up to 2023.1.0
structlog>=22.2.0      # bw2data: logger calls with positional arguments fail up to 22.1.0
voluptuous>=0.12.0     # bw2data: collections.Mapping in 0.11.5
tqdm>=4.21.0           # bw2data: edges_to_dataframe fails up to 4.20.0
xarray>=0.21.0         # bw2calc: 0.20.0 calls Index.get_loc(method=), gone in pandas 2
threadpoolctl>=3.0.0   # bw2calc: ThreadpoolController
ipython>=7.6.0         # bw_timex: asyncio.coroutine up to 7.5.0
ipywidgets>=7.5.0      # bw_timex: collections.Mapping up to 7.4.2
seaborn>=0.12.0        # bw_timex: matplotlib.cm.register_cmap in 0.11.2
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
[ "$column" != suites ] || exec sh scripts/compat-suites.sh "$py" "$out"
BWBENCH_STRICT=${BWBENCH_STRICT-1} PYTHONPATH=benchmarks "$py" -m pytest -p no:cacheprovider --rootdir benchmarks/codspeed benchmarks/codspeed -v
