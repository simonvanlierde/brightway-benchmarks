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
knobs=()
while IFS='=' read -r name value; do
  knobs+=("$name=$value")
done < <(env | grep '^BWBENCH_' || true)

if command -v oss-bench >/dev/null; then
  OSS_BENCH_IMAGE=$image exec oss-bench "$repo" env "${knobs[@]}" scripts/in-box.sh "$@"
fi
exec docker run --rm -i --name "tmp-bwbench-$$" --memory "${BWBENCH_MEM:-2g}" --cpus "${BWBENCH_CPUS:-2}" --user "$(id -u):$(id -g)" \
  -v "$repo":/src -w /src "$image" env "${knobs[@]}" scripts/in-box.sh "$@"
