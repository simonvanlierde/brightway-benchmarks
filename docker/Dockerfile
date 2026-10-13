# The benchmark box: uv's Python 3.12 image plus what scikit-umfpack needs to build
# (it has no Linux wheels). git comes with the base image; asv clones with it.
# Pinned by digest (looked up 2026-10-13), so a rebuilt image has the same base. Move it on purpose.
FROM ghcr.io/astral-sh/uv:python3.12-trixie@sha256:6fbe5da29909abd8ae455ebef9c18ae5d008788997bbf2a6d60ace0890f3905a
RUN apt-get update \
 && apt-get install -y --no-install-recommends swig libsuitesparse-dev pkg-config \
 && rm -rf /var/lib/apt/lists/*
