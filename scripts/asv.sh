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
conf=asv/$subject.json
asv() { uvx --quiet --from asv==0.6.6 asv "$@"; }

# One run per subject at a time: two would rebuild the same environments under each other.
exec 9>".asv/$subject.lock"
flock -n 9 || {
  echo "asv.sh: another $subject run holds .asv/$subject.lock" >&2
  exit 1
}

if [ "$subject" = bw2calc ]; then
  default=umfpack
  [ "$(uname -m)" = x86_64 ] && default=pypardiso,$default
  conf=asv/.bw2calc.local.json
  BWBENCH_SOLVERS=${BWBENCH_SOLVERS:-$default} python3 - <<'PY'
import json, os
conf = json.load(open("asv/bw2calc.json"))
wanted = os.environ["BWBENCH_SOLVERS"].split(",")
name = {"pypardiso": "pypardiso", "scikit-umfpack": "umfpack"}
conf["include"] = [e for e in conf["include"] if all(name[k] in wanted for k in e["req"] if k in name)]
json.dump(conf, open("asv/.bw2calc.local.json", "w"), indent=2)
PY
fi

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
  out=results/$subject/$machine
  mkdir -p "$out"
  for info in .asv/env/"$subject"/*/asv-env-info.json; do
    [ -e "$info" ] || continue
    env=$(dirname "$info")
    { cat "$info" && echo && "$env/bin/python" -m pip freeze; } >"$out/versions-${env##*/}.txt"
  done
fi
exit $status
