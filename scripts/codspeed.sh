#!/bin/sh
# One suite under pytest-codspeed's CPU simulation, inside the codspeed box:
# scripts/codspeed.sh SUBJECT [PACKAGE...]
#
# Installs the suite's environment with scripts/codspeed-venv.sh (see there for what goes in).
# PACKAGEs come on top, e.g. a solver (pypardiso, scikit-umfpack). CodSpeed counts
# instructions, not seconds, so the result does not depend on the machine's load. The profile
# goes to .asv/codspeed/SUBJECT[-PACKAGE...]/; nothing is uploaded.
set -eu
subject=$1
shift
venv=/tmp/codspeed-venv
sh scripts/codspeed-venv.sh "$venv" "$subject" "$@"

# The runner calls whoami, and the container's uid has no passwd entry.
shim=/tmp/codspeed-shim
mkdir -p "$shim"
printf '#!/bin/sh\necho bench\n' >"$shim/whoami"
chmod +x "$shim/whoami"

out=.asv/codspeed/$subject
[ $# -eq 0 ] || out=$out$(printf -- '-%s' "$@" | tr '=<>' '___')
rm -rf "$out" && mkdir -p "$out"
uv pip freeze --python "$venv/bin/python" >"$out/freeze.txt"
PATH=$shim:$venv/bin:$PATH PYTHONPATH=benchmarks codspeed run --mode simulation --skip-upload \
    --profile-folder "/src/$out" -- \
    pytest -p no:cacheprovider --rootdir benchmarks/codspeed "benchmarks/codspeed/test_$subject.py" --codspeed -v

# Instructions per benchmark, from the callgrind files. pytest-codspeed 5.0.3 reports
# "0 benchmarked" for pedantic benchmarks, which it does measure.
awk '/^desc: Trigger: Client Request: benchmarks/ { sub(/^desc: Trigger: Client Request: /, ""); name = $0 }
     /^totals:/ { if (name != "") printf "%d\t%s\n", $2, name; name = "" }' "$out"/[0-9]*.out |
    tee "$out/instructions.tsv"
