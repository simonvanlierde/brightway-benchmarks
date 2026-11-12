#!/bin/sh
# Inside the box: scripts/profile.sh SUBJECT CASE [release=X] [with=PACKAGE...] [NAME=VALUE...]
#
# Installs SUBJECT's environment as the CodSpeed box does (scripts/codspeed-venv.sh): SUBJECT at
# release=X, else the latest at the cutoff; each with=PACKAGE on top, such as the solver a finding
# is about (without one, bw2calc falls back to SciPy's SuperLU); and pyinstrument. Then it profiles
# one case (src/bwbench/profiling.py) at the NAME=VALUE parameters. py-spy would need ptrace,
# which the box drops.
set -eu
subject=$1 case=$2
shift 2
pin='' packages='' params=''
for a in "$@"; do
    case $a in
    release=*) pin="$subject==${a#release=}" ;;
    with=*) packages="$packages ${a#with=}" ;;
    ?*=*) params="$params $a" ;;
    *)
        echo "profile.sh: $a is not release=X, with=PACKAGE or NAME=VALUE" >&2
        exit 2
        ;;
    esac
done
# On disk beside the uv cache, not in the tmpfs /tmp, whose pages count against the box memory.
venv=$PWD/.asv/venvs/profile
rm -rf "$venv"
# shellcheck disable=SC2086 # $pin, $packages and $params are lists of words
sh scripts/codspeed-venv.sh "$venv" "$subject" $pin $packages
# Keep in step with the pyinstrument pin in pyproject.toml.
uv pip install -q --python "$venv/bin/python" pyinstrument==5.1.3
# shellcheck disable=SC2086
BWBENCH_PROFILE_WITH="$packages" PYTHONPATH=src "$venv/bin/python" -m bwbench.profiling "$subject" "$case" $params
