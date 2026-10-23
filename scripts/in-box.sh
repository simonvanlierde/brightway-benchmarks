#!/bin/sh
# Container side of box.sh: keep asv's machine file, uv's cache and the generated
# datapackages inside the mounted repo (all under .asv/, which git ignores).
set -eu
export HOME=/src/.asv/home UV_CACHE_DIR=/src/.asv/uv-cache
# Install only what was on PyPI at this date: uv for asv itself and `uv run --with`,
# pip for asv's environments. Move it on purpose, together with the pins in asv/*.json.
cutoff=2026-10-06T00:00:00Z
export UV_EXCLUDE_NEWER="${UV_EXCLUDE_NEWER:-$cutoff}" PIP_UPLOADED_PRIOR_TO="${PIP_UPLOADED_PRIOR_TO:-$cutoff}"
mkdir -p "$HOME"
# Pin the BLAS and OpenMP threads before asv starts: asv's runner loads numpy before any
# benchmark module, so the pin in bwbench comes too late there.
threads=${BWBENCH_THREADS:-1}
export OPENBLAS_NUM_THREADS="$threads" MKL_NUM_THREADS="$threads" OMP_NUM_THREADS="$threads"
# A fixed hash seed keeps set and dict order of str keys the same from run to run (bw2data and
# bw_processing iterate such sets). Faulthandler prints a traceback when MKL or UMFPACK crash.
export PYTHONHASHSEED=0 PYTHONFAULTHANDLER=1
# asv's clones are owned by the host uid, which has no passwd entry in the container.
# -C /: a worktree's .git file points outside the mount, and git would die on it from /src.
git -C / config --global --get safe.directory >/dev/null || git -C / config --global --add safe.directory "*"
exec "$@"
