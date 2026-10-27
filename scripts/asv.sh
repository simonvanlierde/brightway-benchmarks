#!/bin/sh
# asv for one subject, inside the box: scripts/asv.sh SUBJECT ASV-COMMAND [ARGS...]
#
# BWBENCH_MACHINE labels the results. It defaults to box-<slot> (box-e0, box-p1-quiet), or
# box without a slot. The container's hostname is <host>-<slot> under oss-bench and <host>-box
# under box.sh, so only its slot is kept: results-commit refuses a name with the host in it.
# BWBENCH_SOLVERS picks the solver environments of bw2calc and bw_graph_tools: superlu (the
# base environment, with neither pypardiso nor umfpack), pypardiso and umfpack. The default
# is all three, without pypardiso off x86_64, where MKL has no wheels. bw2calc also has two
# experimental columns, run only when named: klu and umfpack-T, patched into bw2calc
# (src/bwbench/solvers.py).
set -eu
subject=$1 cmd=$2
shift 2
host=$(uname -n) quiet=
case $host in *-quiet) host=${host%-quiet} quiet=-quiet ;; esac
case $host in *-[pe][0-9]) slot=-${host##*-}$quiet ;; *) slot= ;; esac
machine=${BWBENCH_MACHINE:-box$slot}
# The same asv_runner as the configs install into each environment. py-rattler builds the
# conda-forge environments (environment_type "rattler", asv/bw2calc-conda.json).
asv() { uvx --quiet --from asv==0.6.6 --with asv-runner==0.2.5 --with py-rattler==0.27.0 asv "$@"; }

# One run per subject at a time: two would rebuild the same environments under each other.
exec 9>".asv/$subject.lock"
flock -n 9 || {
    echo "asv.sh: another $subject run holds .asv/$subject.lock" >&2
    exit 1
}

# The config asv reads: the solver environments filtered by BWBENCH_SOLVERS, and
# smoke, noise and stack results kept under .asv/<machine>/, out of results/ and so out of the site.
default=superlu,umfpack
[ "$(uname -m)" = x86_64 ] && default=superlu,pypardiso,umfpack
# Written to .asv/ (writable in the box), so asv/ with the tracked configs can stay read-only.
conf=.asv/.$subject.local.json
printed=$(
    BWBENCH_SOLVERS=${BWBENCH_SOLVERS:-$default} python3 - "$subject" "$machine" <<'PY'
import hashlib, json, os, platform, sys
subject, machine = sys.argv[1:]
conf = json.load(open(f"asv/{subject}.json"))
wanted = os.environ["BWBENCH_SOLVERS"].split(",")
unknown = set(wanted) - {"superlu", "pypardiso", "umfpack", "klu", "umfpack-T"}
if unknown or not wanted:
    sys.exit(f"asv.sh: BWBENCH_SOLVERS takes superlu, pypardiso, umfpack, klu and umfpack-T, not {','.join(sorted(unknown))}")
for x86_only in ("pypardiso", "klu"):
    if x86_only in wanted and platform.machine() != "x86_64":
        sys.exit(f"asv.sh: {x86_only} has wheels for x86_64 only")
# asv names an environment after its matrix, not after the stack file it installs. A hash
# of the stack in the name rebuilds the environments when the stack changes, and keeps a
# resumed run from counting results made on the old stack as done.
stack = hashlib.sha256(open(f"asv/{subject}.stack.txt", "rb").read()).hexdigest()[:8]
conf["matrix"]["env"] = {"BWBENCH_STACK": [stack]}
# Added to an entry's own env, not in place of it: the env is part of the environment's
# name, so the entries without one keep the names their results are filed under.
for e in conf.get("include", []):
    e.setdefault("env", {})["BWBENCH_STACK"] = stack
name = {"pypardiso": "pypardiso", "scikit-umfpack": "umfpack"}


def solvers(e: dict) -> set:
    # A patched solver's entry installs the library it patches in (umfpack-T: scikit-umfpack).
    if "BWBENCH_SOLVER" in e["env"]:
        return {e["env"]["BWBENCH_SOLVER"]}
    return {name[k] for k in e["req"] if k in name}


if conf.get("include"):
    conf["include"] = [e for e in conf["include"] if solvers(e) <= set(wanted)]
    if "superlu" not in wanted:
        conf["exclude"] = [{"python": ".*"}]  # asv excludes from the matrix only, never an include
if machine in ("smoke", "noise", "stack"):
    conf["results_dir"] = f"../.asv/{machine}/{subject}"
json.dump(conf, open(f".asv/.{subject}.local.json", "w"), indent=2)
print(stack, f".asv/{conf['results_dir']}")
PY
)
stack=${printed%% *} results=${printed#* }

grep -qs "\"$machine\"" "$HOME/.asv-machine.json" ||
    asv machine --yes --machine "$machine" --config "$conf" >/dev/null
# The klu and umfpack-T entries set BWBENCH_SOLVER in their own env. One left in the caller's
# shell would reach every environment and patch the stock umfpack one without a word.
unset BWBENCH_SOLVER
status=0
case $cmd in
run | continuous | compare) asv "$cmd" --config "$conf" --machine "$machine" "$@" || status=$? ;;
*) asv "$cmd" --config "$conf" "$@" || status=$? ;;
esac

# Record what each environment holds next to the results: a lock file, or for conda a versions
# file. asv reinstalls only the subject per commit, so this is the state after the last commit it installed.
if [ "$cmd" = run ]; then
    out=$results/$machine
    mkdir -p "$out"
    for info in .asv/env/"$subject"/*/asv-env-info.json; do
        [ -e "$info" ] || continue
        env=$(dirname "$info")
        # A folder of an older stack is no longer used, and its packages are not what ran.
        grep -q "\"BWBENCH_STACK\": *\"$stack\"" "$info" || continue
        # A conda environment has no lock: its versions file lists its packages as
        # name-version-build (the build names the BLAS). PEP 751 describes PyPI files only.
        if [ -d "$env/conda-meta" ]; then
            {
                cat "$info" && echo && "$env/bin/python" -m pip freeze
                for pkg in "$env"/conda-meta/*.json; do basename "$pkg" .json; done
            } >"$out/versions-${env##*/}.txt"
            continue
        fi
        # A PyPI environment: a PEP 751 lock file, with each package's index URL and hashes. The subject
        # is left out: asv built it from the commit its result names, which need not be a release.
        # asv names environment folders by a hex hash, which PEP 751's "pylock.<name>.toml" allows.
        lock=$out/pylock.${env##*/}.toml
        "$env/bin/python" -m pip freeze | grep -iv "^${subject}[ =@]" |
            uv pip compile --quiet --no-deps --python "$env/bin/python" --no-header -o "$lock" - ||
            status=1
    done
    # What ran, as one RO-Crate over every subject. It sits above the subjects' asv folders,
    # where asv looks for no results.
    uv run --quiet --no-project --with numpy==2.5.3 --with scipy==1.18.1 python scripts/run_crate.py "$(dirname "$results")" ||
        status=1
fi
exit $status
