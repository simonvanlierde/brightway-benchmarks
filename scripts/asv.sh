#!/bin/sh
# asv for one subject, inside the box: scripts/asv.sh SUBJECT ASV-COMMAND [ARGS...]
#
# BWBENCH_MACHINE labels the results: set it per host and CPU slot.
# BWBENCH_SOLVERS (bw2calc only) adds environments with pypardiso and/or umfpack. The
# base environment has neither, so bw2calc falls back to SuperLU there. The default leaves
# out pypardiso off x86_64, where MKL has no wheels.
set -eu
subject=$1 cmd=$2
shift 2
machine=${BWBENCH_MACHINE:-local}
conf=asv/$subject.json
asv() { uvx --quiet --from asv==0.6.6 asv "$@"; }

if [ "$subject" = bw2calc ]; then
  default=umfpack
  [ "$(uname -m)" = x86_64 ] && default=pypardiso,$default
  conf=asv/.bw2calc.local.json
  BWBENCH_SOLVERS=${BWBENCH_SOLVERS:-$default} python3 - <<'PY'
import json, os
conf = json.load(open("asv/bw2calc.json"))
wanted = os.environ["BWBENCH_SOLVERS"].split(",")
name = {"pypardiso": "pypardiso", "scikit-umfpack": "umfpack"}
conf["include"] = [e for e in conf["include"] if all(name[k] in wanted for k in e["req"])]
json.dump(conf, open("asv/.bw2calc.local.json", "w"), indent=2)
PY
fi

grep -qs "\"$machine\"" "$HOME/.asv-machine.json" ||
  asv machine --yes --machine "$machine" --config "$conf" >/dev/null
case $cmd in
run | continuous | compare) asv "$cmd" --config "$conf" --machine "$machine" "$@" ;;
*) asv "$cmd" --config "$conf" "$@" ;;
esac
