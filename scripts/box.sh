#!/usr/bin/env bash
# Run a command in a throwaway container that sees only this repo. Brightway's code
# (installed by asv into its environments) never runs on the host.
#
# On a host with `oss-bench` (the devbox) the container gets a pinned CPU slot;
# elsewhere it is a plain `docker run`. BWBENCH_* variables are passed through.
set -euo pipefail
repo=$(cd "$(dirname "$0")/.." && pwd)
image=${BWBENCH_IMAGE:-bwbench-box}
[ "$image" != bwbench-box ] || docker image inspect bwbench-box >/dev/null 2>&1 ||
    docker build -q -t bwbench-box "$repo/docker" >/dev/null
# ${knobs[@]+...} below: bash 3.2 (macOS) treats an empty array as unset under `set -u`.
knobs=()
while IFS='=' read -r name value; do
    knobs+=("$name=$value")
done < <(env | grep '^BWBENCH_' || true)

if command -v oss-bench >/dev/null; then
    # NOTE: oss-bench mounts the whole repo read-write (it has no option for a read-only
    # mount); it drops capabilities and caps processes itself.
    OSS_BENCH_IMAGE=$image exec oss-bench "$repo" env ${knobs[@]+"${knobs[@]}"} scripts/in-box.sh "$@"
fi
# The repo is read-only in the box, so code asv installs cannot change what the host
# later runs (.git, .venv, justfile, scripts/). Only asv's working folders are writable.
mounts=(-v "$repo":/src:ro)
for d in .asv results site asv; do
    mkdir -p "$repo/$d"
    mounts+=(-v "$repo/$d":"/src/$d")
done
exec docker run --rm -i --init --name "tmp-bwbench-$$" --user "$(id -u):$(id -g)" \
    --cap-drop ALL --security-opt no-new-privileges --pids-limit 4096 \
    --memory "${BWBENCH_MEM:-2g}" --cpus "${BWBENCH_CPUS:-2}" \
    "${mounts[@]}" -w /src "$image" env ${knobs[@]+"${knobs[@]}"} scripts/in-box.sh "$@"
