#!/bin/sh
# The environment one pytest-codspeed suite runs in: scripts/codspeed-venv.sh VENV SUBJECT [PACKAGE...]
#
# Installs what asv installs for SUBJECT's latest release: the fixed stack, the matrix
# requirements from asv/SUBJECT.json, and SUBJECT itself as on PyPI at the cutoff in
# UV_EXCLUDE_NEWER (in-box.sh's, or the CodSpeed workflow's). PACKAGEs come on top, e.g. a
# solver (pypardiso, scikit-umfpack). A PACKAGE that pins SUBJECT (bw2calc==3.0.0) replaces
# the latest release and may be newer than the cutoff; its own new dependencies come with it.
# Shared by scripts/codspeed.sh (the local box) and .github/workflows/codspeed.yml (CI).
set -eu
venv=$1
subject=$2
shift 2
spec=$subject
newer=
for p in "$@"; do
    case $p in "$subject=="*)
        spec=$p
        newer="--exclude-newer-package $subject=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
        ;;
    esac
done
uv venv -q "$venv" --python 3.12
py=$venv/bin/python
reqs=$(python3 -c '
import json, sys
req = json.load(open(f"asv/{sys.argv[1]}.json"))["matrix"]["req"]
print(" ".join(f"{k}=={v[0]}" for k, v in req.items() if not k.startswith("pip+")))
' "$subject")
# shellcheck disable=SC2086 # $reqs and $newer are lists of words
uv pip install -q --python "$py" $newer --no-deps -r "asv/$subject.stack.txt" $reqs "$spec"
# shellcheck disable=SC2086
uv pip install -q --python "$py" $newer -c "asv/$subject.stack.txt" pytest pytest-codspeed==5.0.3 "$@"
