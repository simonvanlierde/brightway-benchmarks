# The benchmark box: uv's Python 3.12 image plus what scikit-umfpack needs to build
# (it has no Linux wheels). git comes with the base image; asv clones with it.
# Pinned by digest (looked up 2026-10-13), so a rebuilt image has the same base. Move it on purpose.
FROM ghcr.io/astral-sh/uv:python3.12-trixie@sha256:6fbe5da29909abd8ae455ebef9c18ae5d008788997bbf2a6d60ace0890f3905a AS box
RUN apt-get update \
 && apt-get install -y --no-install-recommends swig libsuitesparse-dev pkg-config \
 && rm -rf /var/lib/apt/lists/*

# The box plus CodSpeed's runner and its valgrind, for `just codspeed` only.
FROM box AS codspeed
ADD --checksum=sha256:20a036dc4a582664e87e48ba3f2be68a51587f7791d8380520dd13e3e1b5ebd7 \
    https://github.com/CodSpeedHQ/codspeed/releases/download/v5.4.2/codspeed-runner-x86_64-unknown-linux-musl.tar.gz /tmp/runner.tgz
# `codspeed setup` builds its valgrind, then fails on a host sysctl (kernel.kptr_restrict) a
# build cannot set; simulation does not need it, so only valgrind's presence is checked.
# libc6-dbg gives valgrind libc's symbols, which the runner says makes the counts more exact.
RUN apt-get update \
 && apt-get install -y --no-install-recommends libc6-dbg \
 && rm -rf /var/lib/apt/lists/* \
 && tar -xzf /tmp/runner.tgz -C /tmp \
 && find /tmp -name codspeed -type f -exec install -m755 {} /usr/local/bin/codspeed \; \
 && rm -rf /tmp/* \
 && (codspeed setup || true) \
 && valgrind --version

# The default build: the box alone.
FROM box
