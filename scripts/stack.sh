#!/bin/sh
# Resolve the fixed stack for one subject, inside the box: scripts/stack.sh SUBJECT
#
# Every release of SUBJECT is benchmarked on the same stack: the dependencies of its latest
# release, at the release cutoff in in-box.sh, with the pins of asv/SUBJECT.json. Only the
# subject itself changes between commits (it installs with --no-deps), so a timing change is
# the subject's. The list is a full resolution and installs with --no-deps, so pip adds
# nothing to it. Packages the config varies on purpose (the solvers, the bw_processing build)
# stay out of the list. Writes .asv/stack/SUBJECT.txt; `just stack` copies it to asv/.
set -eu
subject=$1
mkdir -p .asv/stack
python3 - "$subject" >.asv/stack/"$subject".in <<'PY'
import json, sys
subject = sys.argv[1]
conf = json.load(open(f"asv/{subject}.json"))
latest = open(f"asv/{subject}.hashes").read().split()[-1].removeprefix("v")
print(f"{subject}=={latest}")
for name, values in conf["matrix"]["req"].items():
    print(f"{name.removeprefix('pip+')}=={values[0]}" if not values[0].startswith("git+") else values[0])
PY
python3 - "$subject" >.asv/stack/"$subject".drop <<'PY'
import json, sys
subject = sys.argv[1]
conf = json.load(open(f"asv/{subject}.json"))
varied = {k for k, v in conf["matrix"]["req"].items() if len(v) > 1}
varied |= {k for env in conf.get("include", []) for k in env["req"]}
# bw2calc's suite never imports bw2data, and bw2calc 2.0 to 2.2 fail to import beside
# bw2data 4.5 or later (they compare its string version with a tuple).
unused = {"bw2calc": {"bw2data"}}.get(subject, set())
for name in {subject, *varied, *unused} - {"numpy", "scipy", "pip+asv_runner"}:
    print(name.removeprefix("pip+").replace("_", "-").lower())
PY
# --universal keeps platform markers, so pip skips x86-only packages (MKL) on ARM.
uv pip compile --quiet --no-header --no-annotate --python-version 3.12 --universal \
    .asv/stack/"$subject".in |
    grep -viE "^($(paste -sd'|' .asv/stack/"$subject".drop))==" >.asv/stack/"$subject".txt
echo "stack.sh: $(wc -l <.asv/stack/"$subject".txt) packages for $subject" >&2
