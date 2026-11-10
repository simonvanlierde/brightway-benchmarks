#!/bin/sh
# Resolve the fixed stack for one subject, inside the box: scripts/stack.sh SUBJECT
#
# Every release of SUBJECT is benchmarked on the same stack: the dependencies of its latest
# release, at the release cutoff in in-box.sh, with the pins of asv/SUBJECT.json. Only the
# subject itself changes between commits (it installs with --no-deps), so a timing change is
# the subject's. The list is a full resolution and installs with --no-deps, so pip adds
# nothing to it. Packages the config varies on purpose (the solvers, the bw_processing build)
# stay out of the list. Writes .asv/stack/SUBJECT.txt; `just stack` copies it to asv/. Its first
# line names the cutoff it was resolved at; tests/test_asv_config.py checks it against in-box.sh's.
set -eu
subject=$1
cutoff=$(sed -n 's/^cutoff=//p' scripts/in-box.sh)
# in-box.sh lets a caller's UV_EXCLUDE_NEWER win, which would resolve at another date than the line says.
[ "${UV_EXCLUDE_NEWER:-}" = "$cutoff" ] || {
    echo "stack.sh: UV_EXCLUDE_NEWER is '${UV_EXCLUDE_NEWER:-}', not in-box.sh's cutoff $cutoff" >&2
    exit 1
}
mkdir -p .asv/stack
python3 scripts/asv_conf.py stack-in "$subject" >.asv/stack/"$subject".in
python3 scripts/asv_conf.py drop "$subject" >.asv/stack/"$subject".drop
# --universal keeps platform markers, so pip skips x86-only packages (MKL) on ARM.
{
    echo "# cutoff $cutoff"
    uv pip compile --quiet --no-header --no-annotate --python-version 3.13 --universal \
        .asv/stack/"$subject".in |
        grep -viE "^($(paste -sd'|' .asv/stack/"$subject".drop))=="
} >.asv/stack/"$subject".txt
echo "stack.sh: $(grep -vc '^#' .asv/stack/"$subject".txt) packages for $subject" >&2
