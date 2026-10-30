#!/bin/sh
# The suites column's test step (scripts/compat.sh PYTHON suites calls it): runs each Brightway
# package's own tests against the set compat.sh installed. scripts/compat-suites.sh PY OUT
#
# Most sdists leave tests out, so the tests come from the package's GitHub tag for the version
# installed (VERSION, or vVERSION as bw_timex names them). Only tests/ and pyproject.toml (some
# tests read it) are unpacked, so pytest imports the installed package, not a source tree
# beside the tests. Of the package's pytest settings only testpaths applies (it names files
# that pytest's default pattern skips); the rest only add coverage. Each result goes to
# OUT/suites.txt, one line per package (NAME VERSION passed|failed|no tag, or NAME not in the
# set; then the failing tests), and pytest's output to OUT/suites/NAME.log. Exits 1 if any
# package failed. Linux only (GNU tar's --wildcards).
set -eu
py=$1
out=$2
# Tests that cannot pass in this run whatever the releases, as pytest node IDs per package,
# each with its reason, as `NAME NODE-ID  # reason`. Keep this short: a failure belongs in the
# report. None so far: every suite runs offline once its tests are unpacked.
cat >"$out/deselect.txt" <<'EOF'
EOF
# The name in requirements.txt (as uv writes it), then the brightway-lca repository.
packages='bw2data:brightway2-data bw2calc:brightway2-calc bw2io:brightway2-io bw-processing:bw_processing
matrix-utils:matrix_utils bw-graph-tools:bw_graph_tools bw-timex:bw_timex'
unset PYTHONPATH
: >"$out/suites.txt"
failed=0
for pkg in $packages; do
    name=${pkg%%:*}
    repo=${pkg#*:}
    version=$(sed -n "s/^$name==//p" "$out/requirements.txt")
    if [ -z "$version" ]; then
        echo "$name not in the set" >>"$out/suites.txt"
        failed=1
        continue
    fi
    dir=$out/suites/$name
    mkdir -p "$dir"
    url=https://github.com/brightway-lca/$repo/archive/refs/tags
    if ! curl -fsSL -o "$dir.tar.gz" "$url/$version.tar.gz" && ! curl -fsSL -o "$dir.tar.gz" "$url/v$version.tar.gz"; then
        echo "$name $version no tag" >>"$out/suites.txt"
        failed=1
        continue
    fi
    tar -xzf "$dir.tar.gz" -C "$dir" --strip-components=1 --wildcards '*/tests/*' '*/pyproject.toml'
    # pytest reads pytest.ini before the pyproject.toml beside it.
    "$py" -c 'import sys, tomllib
pytest = tomllib.load(open(sys.argv[1], "rb")).get("tool", {}).get("pytest", {})
paths = pytest.get("ini_options", {}).get("testpaths", ["tests"])
print("[pytest]\ntestpaths =", *paths)' "$dir/pyproject.toml" >"$dir/pytest.ini"
    set -f # node IDs hold [ ]
    deselect=$(sed -n "s|^$name \([^ ]*\).*|--deselect \1|p" "$out/deselect.txt")
    rc=0
    # shellcheck disable=SC2086 # one word per --deselect and node ID
    (cd "$dir" && "$py" -m pytest -p no:cacheprovider -rfE $deselect) >"$dir.log" 2>&1 || rc=$?
    set +f
    rm -rf "$dir" "$dir.tar.gz" # the log is what the artifact needs
    cat "$dir.log"
    if [ "$rc" = 0 ]; then
        echo "$name $version passed" >>"$out/suites.txt"
    else
        echo "$name $version failed" >>"$out/suites.txt"
        sed -nE 's/^(FAILED|ERROR) ([^ ]*).*/    \1 \2/p' "$dir.log" >>"$out/suites.txt"
        failed=1
    fi
done
printf "bw2calc 0.0 failed\n    FAILED tests/test_forced.py::test_forced\n" >>"$out/suites.txt" # TEMP forcing
failed=1
cat "$out/suites.txt"
exit "$failed"
