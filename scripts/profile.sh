#!/bin/sh
# Inside the box: scripts/profile.sh SUBJECT CASE SIZE RELEASE [NAME=VALUE...]
#
# Installs SUBJECT's environment as the CodSpeed box does (scripts/codspeed-venv.sh), SUBJECT at
# RELEASE unless that is empty (the latest at the cutoff), and pyinstrument on top, then profiles
# one case (src/bwbench/profiling.py). py-spy would need ptrace, which the box drops.
set -eu
subject=$1 case=$2 size=$3 release=$4
shift 4
venv=/tmp/profile-venv
if [ -n "$release" ]; then
    sh scripts/codspeed-venv.sh "$venv" "$subject" "$subject==$release"
else
    sh scripts/codspeed-venv.sh "$venv" "$subject"
fi
uv pip install -q --python "$venv/bin/python" pyinstrument==5.1.3
PYTHONPATH=src "$venv/bin/python" -m bwbench.profiling "$subject" "$case" "$size" "$@"
