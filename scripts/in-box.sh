#!/bin/sh
# Container side of box.sh: keep asv's machine file, uv's cache and the generated
# datapackages inside the mounted repo (all under .asv/, which git ignores).
set -eu
export HOME=/src/.asv/home UV_CACHE_DIR=/src/.asv/uv-cache
export BWBENCH_DATA="${BWBENCH_DATA:-/src/.asv/data}"
mkdir -p "$HOME"
# asv's clones are owned by the host uid, which has no passwd entry in the container.
git config --global --get safe.directory >/dev/null || git config --global --add safe.directory "*"
exec "$@"
