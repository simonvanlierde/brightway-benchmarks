# The benchmark box: uv's Python 3.13 image plus what scikit-umfpack needs to build
# (it has no Linux wheels). git comes with the base image; asv clones with it.
# Pinned by digest (looked up 2026-11-09), so a rebuilt image has the same base. Move it on purpose.
FROM ghcr.io/astral-sh/uv:python3.13-trixie@sha256:6299696d13e91e9d58e910fca4e503e89f217229a2c4c840a11b367dc24816f4 AS box
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

# The conda-forge compat column (`just compat 3.13 conda-forge`): pixi on Ubuntu, nothing from
# PyPI. Pinned by digest (looked up 2026-10-29).
FROM ghcr.io/prefix-dev/pixi:0.82.0@sha256:e6cca082e52de275f4e6fb4e6648522f30e4ed334fed37378cde393e07405200 AS conda

# The default build: the box alone.
FROM box
