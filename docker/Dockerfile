# The benchmark box: uv's Python 3.12 image plus what scikit-umfpack needs to build
# (it has no Linux wheels). git comes with the base image; asv clones with it.
FROM ghcr.io/astral-sh/uv:python3.12-trixie
RUN apt-get update \
 && apt-get install -y --no-install-recommends swig libsuitesparse-dev pkg-config \
 && rm -rf /var/lib/apt/lists/*
