#!/bin/sh
# One suite under pytest-codspeed's CPU simulation, inside the codspeed box:
# scripts/codspeed.sh SUBJECT [PACKAGE...]
#
# Installs what asv installs for SUBJECT's latest release: the fixed stack, the matrix
# requirements from asv/SUBJECT.json, and SUBJECT itself as on PyPI at in-box.sh's cutoff.
# PACKAGEs come on top, e.g. a solver (pypardiso, scikit-umfpack). CodSpeed counts
# instructions, not seconds, so the result does not depend on the machine's load. The
# profile goes to .asv/codspeed/SUBJECT[-PACKAGE...]/; nothing is uploaded.
set -eu
subject=$1
shift
venv=/tmp/codspeed-venv
uv venv -q "$venv" --python 3.12
py=$venv/bin/python
reqs=$(python3 -c '
import json, sys
req = json.load(open(f"asv/{sys.argv[1]}.json"))["matrix"]["req"]
print(" ".join(f"{k}=={v[0]}" for k, v in req.items() if not k.startswith("pip+")))
' "$subject")
# shellcheck disable=SC2086 # $reqs is a list of requirements
uv pip install -q --python "$py" --no-deps -r "asv/$subject.stack.txt" $reqs "$subject"
uv pip install -q --python "$py" -c "asv/$subject.stack.txt" pytest pytest-codspeed==5.0.3 "$@"

# The runner calls whoami, and the container's uid has no passwd entry.
shim=/tmp/codspeed-shim
mkdir -p "$shim"
printf '#!/bin/sh\necho bench\n' >"$shim/whoami"
# The runner turns ASLR off with `setarch -R`, which docker's seccomp profile refuses. So
# this runs the command with ASLR on, which costs some run-to-run spread in the counts.
cat >"$shim/setarch" <<'SH'
#!/bin/sh
shift
while [ "${1#-}" != "$1" ]; do shift; done
exec "$@"
SH
chmod +x "$shim/whoami" "$shim/setarch"

out=.asv/codspeed/$subject
[ $# -eq 0 ] || out=$out$(printf -- '-%s' "$@" | tr '=<>' '___')
rm -rf "$out" && mkdir -p "$out"
uv pip freeze --python "$py" >"$out/freeze.txt"
PATH=$shim:$venv/bin:$PATH PYTHONPATH=benchmarks codspeed run --mode simulation --skip-upload \
    --profile-folder "/src/$out" -- \
    pytest -p no:cacheprovider --rootdir benchmarks/codspeed "benchmarks/codspeed/test_$subject.py" --codspeed -v

# Instructions per benchmark, from the callgrind files. pytest-codspeed 5.0.3 reports
# "0 benchmarked" for pedantic benchmarks, which it does measure.
awk '/^desc: Trigger: Client Request: benchmarks/ { sub(/^desc: Trigger: Client Request: /, ""); name = $0 }
     /^totals:/ { if (name != "") printf "%d\t%s\n", $2, name; name = "" }' "$out"/[0-9]*.out |
    tee "$out/instructions.tsv"
