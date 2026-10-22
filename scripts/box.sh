#!/usr/bin/env bash
# Run a command in a throwaway container that sees only this repo. Brightway's code
# (installed by asv into its environments) never runs on the host.
#
# On a host with `oss-bench` (a CPU-slot runner from the author's dotfiles) the container gets a pinned CPU slot;
# elsewhere it is a plain `docker run`. BWBENCH_* variables are passed through.
set -euo pipefail
repo=$(cd "$(dirname "$0")/.." && pwd)
# Tagged by the Dockerfile's checksum, so an edited Dockerfile gets a fresh build.
# BWBENCH_TARGET picks the Dockerfile stage: box (the default) or codspeed.
target=${BWBENCH_TARGET:-box}
image=bwbench-$target:$(cksum <"$repo/docker/Dockerfile" | cut -d' ' -f1)
if ! docker image inspect "$image" >/dev/null 2>&1; then
    echo "box.sh: building the $target image $image (a few minutes, once)" >&2
    docker build -q --target "$target" -t "$image" "$repo/docker" >/dev/null
fi
# ${knobs[@]+...} below: bash 3.2 (macOS) treats an empty array as unset under `set -u`.
knobs=()
while IFS='=' read -r name value; do
    knobs+=("$name=$value")
done < <(env | grep '^BWBENCH_' || true)

# The repo is read-only in the box, so code asv installs cannot change what the host later
# runs (.git, .venv, justfile, scripts/, the asv/ configs). Only these folders are writable.
writable=".asv results site"

# An oss-bench without OSS_BENCH_RW would mount the repo read-write, so use it only if it has it.
if command -v oss-bench >/dev/null && grep -q OSS_BENCH_RW "$(command -v oss-bench)"; then
    # oss-bench drops capabilities and caps processes itself.
    OSS_BENCH_IMAGE=$image OSS_BENCH_RW=$writable exec oss-bench "$repo" \
        env ${knobs[@]+"${knobs[@]}"} scripts/in-box.sh "$@"
fi
mounts=(-v "$repo":/src:ro)
for d in $writable; do
    mkdir -p "$repo/$d"
    mounts+=(-v "$repo/$d":"/src/$d")
done
exec docker run --rm -i --init --name "tmp-bwbench-$$" --hostname "$(hostname -s)-box" --user "$(id -u):$(id -g)" \
    --cap-drop ALL --security-opt no-new-privileges --pids-limit 4096 \
    --memory "${BWBENCH_MEM:-2g}" --memory-swap "${BWBENCH_MEM:-2g}" --cpus "${BWBENCH_CPUS:-2}" \
    "${mounts[@]}" -w /src "$image" env ${knobs[@]+"${knobs[@]}"} scripts/in-box.sh "$@"
