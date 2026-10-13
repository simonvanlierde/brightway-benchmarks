#!/bin/sh
# asv for one subject, inside the box: scripts/asv.sh SUBJECT ASV-COMMAND [ARGS...]
#
# BWBENCH_MACHINE labels the results. It defaults to the container's hostname, which
# oss-bench sets to <host>-<slot> and box.sh to <host>-box.
# BWBENCH_SOLVERS (bw2calc only) adds environments with pypardiso and/or umfpack. The
# base environment has neither, so bw2calc falls back to SuperLU there. The default leaves
# out pypardiso off x86_64, where MKL has no wheels.
set -eu
subject=$1 cmd=$2
shift 2
machine=${BWBENCH_MACHINE:-$(uname -n)}
asv() { uvx --quiet --from asv==0.6.6 asv "$@"; }

# One run per subject at a time: two would rebuild the same environments under each other.
exec 9>".asv/$subject.lock"
flock -n 9 || {
    echo "asv.sh: another $subject run holds .asv/$subject.lock" >&2
    exit 1
}

# The config asv reads: bw2calc's solver environments filtered by BWBENCH_SOLVERS, and
# smoke results kept under .asv/smoke/, out of results/ and so out of the site.
default=umfpack
[ "$(uname -m)" = x86_64 ] && default=pypardiso,$default
conf=asv/.$subject.local.json
results=$(
    BWBENCH_SOLVERS=${BWBENCH_SOLVERS:-$default} python3 - "$subject" "$machine" <<'PY'
import json, os, sys
subject, machine = sys.argv[1:]
conf = json.load(open(f"asv/{subject}.json"))
wanted = os.environ["BWBENCH_SOLVERS"].split(",")
name = {"pypardiso": "pypardiso", "scikit-umfpack": "umfpack"}
conf["include"] = [e for e in conf.get("include", []) if all(name[k] in wanted for k in e["req"] if k in name)]
if machine == "smoke":
    conf["results_dir"] = f"../.asv/smoke/{subject}"
json.dump(conf, open(f"asv/.{subject}.local.json", "w"), indent=2)
print(f"asv/{conf['results_dir']}")
PY
)

grep -qs "\"$machine\"" "$HOME/.asv-machine.json" ||
    asv machine --yes --machine "$machine" --config "$conf" >/dev/null
status=0
case $cmd in
run | continuous | compare) asv "$cmd" --config "$conf" --machine "$machine" "$@" || status=$? ;;
*) asv "$cmd" --config "$conf" "$@" || status=$? ;;
esac

# Record what each environment holds next to the results. asv reinstalls only the
# subject per commit, so this is the state after the last commit it installed.
if [ "$cmd" = run ]; then
    out=$results/$machine
    mkdir -p "$out"
    for info in .asv/env/"$subject"/*/asv-env-info.json; do
        [ -e "$info" ] || continue
        env=$(dirname "$info")
        { cat "$info" && echo && "$env/bin/python" -m pip freeze; } >"$out/versions-${env##*/}.txt"
        # The same as a PEP 751 lock file, with each package's index URL and hashes. The subject
        # is left out: asv built it from the commit its result names, as a local wheel.
        "$env/bin/python" -m pip freeze | grep -v ' @ file:' |
            uv pip compile --quiet --python "$env/bin/python" --no-header -o "$out/pylock.${env##*/}.toml" - ||
            status=1
    done
    # What ran, as an RO-Crate next to the results.
    uv run --quiet --no-project --with numpy==2.5.3 --with scipy==1.18.1 python scripts/run_crate.py "$out" || status=1
fi
exit $status
