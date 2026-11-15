#!/usr/bin/env bash
# Run a command in a throwaway container that sees only this repo. Brightway's code
# (installed by asv into its environments) never runs on the host.
#
# A plain `docker run` by default. A host can hand the run to its own runner instead, to pin the
# box to a CPU slot, say: BWBENCH_RUNNER, or `bwbench-runner` on PATH (BWBENCH_RUNNER= turns that
# off). It is called as `RUNNER REPO CMD...` with BWBENCH_RUNNER_IMAGE (the image),
# BWBENCH_RUNNER_RW (the folders it mounts writable; the rest of the repo read-only),
# BWBENCH_RUNNER_TMPFS (the size of /tmp, a tmpfs that allows exec), BWBENCH_RUNNER_MEM (only when
# BWBENCH_MEM is set) and BWBENCH_RUNNER_NOASLR=1 (codspeed: it must allow personality(ADDR_NO_RANDOMIZE)).
# It drops capabilities and caps processes as the docker run below does. BWBENCH_* variables are passed through.
set -euo pipefail
repo=$(cd "$(dirname "$0")/.." && pwd)
# BWBENCH_TARGET picks the Dockerfile stage: box (the default), codspeed or conda. Its tag is the
# checksum of that stage's instructions and those of the stages it builds on, comments left out,
# so an edit to the codspeed or conda stage leaves the box image, and the queue jobs pinned to it, alone.
target=${BWBENCH_TARGET:-box}
stage() {
    local base
    base=$(awk -v s="$1" 'toupper($1) == "FROM" && $NF == s && toupper($(NF - 1)) == "AS" { print $2; exit }' "$repo/docker/Dockerfile")
    if [ -n "$base" ] && [ "$base" != "$1" ] && grep -qiE "^FROM .* AS $base\$" "$repo/docker/Dockerfile"; then
        stage "$base"
    fi
    awk -v s="$1" 'toupper($1) == "FROM" { on = ($NF == s && toupper($(NF - 1)) == "AS") } on && NF && $1 !~ /^#/' "$repo/docker/Dockerfile"
}
image=bwbench-$target:$(stage "$target" | cksum | cut -d' ' -f1)
if ! docker image inspect "$image" >/dev/null 2>&1; then
    echo "box.sh: building the $target image $image (a few minutes, once)" >&2
    docker build -q --target "$target" -t "$image" "$repo/docker" >/dev/null
fi
# `box.sh --image` only builds the image if it is missing and prints its name, for a plain docker run.
if [ "${1:-}" = --image ]; then
    echo "$image"
    exit 0
fi
# CodSpeed's runner turns address randomization (ASLR) off with `setarch -R`, which Docker's
# default seccomp profile refuses. The codspeed box runs under docker/seccomp-noaslr.json
# (`just seccomp-profile`): the default profile plus one rule that allows
# personality(ADDR_NO_RANDOMIZE). Seccomp itself stays on.
# ${knobs[@]+...} below: bash 3.2 (macOS) treats an empty array as unset under `set -u`.
# asv.sh records which commit wrote each result. git cannot tell it from inside the box when
# this is a worktree, whose .git file points outside the mount.
BWBENCH_COMMIT=${BWBENCH_COMMIT:-$(git -C "$repo" rev-parse HEAD 2>/dev/null || true)}
export BWBENCH_COMMIT
# BWBENCH_ENERGY=1 shows the box the CPU package's energy counter (Intel RAPL), read-only. Docker
# hides /sys/devices/virtual/powercap in every container, so it is mounted at /run/rapl instead.
# On the host BWBENCH_RAPL names the counter's folder, for the test.
energy=() cpus=${BWBENCH_CPUSET:-}
if [ "${BWBENCH_ENERGY:-}" = 1 ]; then
    rapl=${BWBENCH_RAPL:-/sys/class/powercap/intel-rapl:0}
    [ -r "$rapl/energy_uj" ] || {
        echo "box.sh: BWBENCH_ENERGY=1 needs a readable $rapl/energy_uj (Intel RAPL)" >&2
        exit 2
    }
    energy=(--mount "type=bind,source=$rapl,target=/run/rapl,readonly" --group-add "$(stat -c %g "$rapl/energy_uj")")
    export BWBENCH_RAPL=/run/rapl
fi
knobs=()
while IFS='=' read -r name value; do
    knobs+=("$name=$value")
done < <(env | grep '^BWBENCH_' || true)

# The repo is read-only in the box, so code asv installs cannot change what the host later
# runs (.git, .venv, justfile, scripts/, the asv/ configs). Only these folders are writable.
writable=".asv results site"
# /tmp is a tmpfs, so the Brightway projects bw2data and bw_timex write (tempfile.mkdtemp, and
# in-box.sh's HOME) never touch the overlay disk. Its pages count against the memory cap, so the
# venvs live under .asv/. It allows exec, as tools may still run programs from /tmp.
tmpfs_size=6g

runner=${BWBENCH_RUNNER-$(command -v bwbench-runner || true)}
# An energy run needs mounts a runner does not take, so it goes to docker.
if [ "${BWBENCH_ENERGY:-}" != 1 ] && [ -n "$runner" ]; then
    export BWBENCH_RUNNER_IMAGE=$image BWBENCH_RUNNER_RW=$writable BWBENCH_RUNNER_TMPFS=$tmpfs_size
    [ "$target" != codspeed ] || export BWBENCH_RUNNER_NOASLR=1
    [ -z "${BWBENCH_MEM:-}" ] || export BWBENCH_RUNNER_MEM=$BWBENCH_MEM
    exec "$runner" "$repo" env ${knobs[@]+"${knobs[@]}"} scripts/in-box.sh "$@"
fi
mounts=(-v "$repo":/src:ro)
noaslr=()
[ "$target" != codspeed ] || noaslr=(--security-opt "seccomp=$repo/docker/seccomp-noaslr.json")
for d in $writable; do
    mkdir -p "$repo/$d"
    mounts+=(-v "$repo/$d":"/src/$d")
done
# The CPU package counter must not see other work, so an energy run waits for a quiet machine:
# BWBENCH_GATE, or `bwbench-gate` on PATH, a program that runs `GATE CMD...` once nothing else runs
# on BWBENCH_GATE_CPUS (inside a gate the caller already holds there, at once). The box runs on
# BWBENCH_CPUSET. Without both there is no energy run.
gate=() g=${BWBENCH_GATE:-$(command -v bwbench-gate || true)}
if [ -n "${energy[*]}" ]; then
    [ -n "$g" ] && [ -x "$g" ] && [ -n "$cpus" ] || {
        echo "box.sh: BWBENCH_ENERGY=1 needs a quiet gate (BWBENCH_GATE or bwbench-gate) and BWBENCH_CPUSET" >&2
        exit 2
    }
    gate=(env BWBENCH_GATE_CPUS="$cpus" "$g")
fi
exec ${gate[@]+"${gate[@]}"} docker run --rm -i --init --name "tmp-bwbench-$$" --hostname "$(hostname -s)-box" --user "$(id -u):$(id -g)" \
    --cap-drop ALL --security-opt no-new-privileges ${noaslr[@]+"${noaslr[@]}"} --pids-limit 4096 \
    ${energy[@]+"${energy[@]}"} ${energy[@]+--cpuset-cpus "$cpus"} \
    --memory "${BWBENCH_MEM:-2g}" --memory-swap "${BWBENCH_MEM:-2g}" --cpus "${BWBENCH_CPUS:-2}" \
    --tmpfs "/tmp:rw,exec,size=$tmpfs_size,mode=1777" \
    "${mounts[@]}" -w /src "$image" env ${knobs[@]+"${knobs[@]}"} scripts/in-box.sh "$@"
