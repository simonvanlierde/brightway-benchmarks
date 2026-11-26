"""Where generated and downloaded files are cached, and the hash that keys them.

Standard library only, like ``bwbench.profiles``.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path


def short_hash(key: object, length: int = 12) -> str:
    """Hex digest of ``key`` as sorted JSON, cut to ``length``: the form of every cache and version key."""
    return hashlib.sha256(json.dumps(key, sort_keys=True).encode()).hexdigest()[:length]


def data_root() -> Path:
    """Where generated datapackages are cached: ``$XDG_CACHE_HOME/bwbench``, by default ``~/.cache/bwbench``.

    The box sets XDG_CACHE_HOME under ``.asv/``, so the cache outlives its per-run home.
    """
    return Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "bwbench"
