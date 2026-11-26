#!/usr/bin/env python3
"""Keep asv's environments in ``.asv/env/`` small: drop stale ones, hardlink identical files.

asv builds one environment per subject and matrix entry and never removes one whose entry left
the config, and its environment type installs the matrix packages with pip, which copies every
file. So the folder only grows, about 300 MB per environment, most of it the same numpy, scipy
and pandas files.

``tidy_envs.py ENV_DIR [--days N]`` removes each environment (``ENV_DIR/<subject>/<hash>/``)
with no file written in the last N days (default 30; asv writes into an environment each time
it installs a commit there, so a quiet one is unused), then replaces identical files across the
rest with hardlinks to one copy. Files are only compared, never imported or run, so it runs on
the host. A hardlink is safe here: pip and Python replace files (unlink, or write and rename)
and never write into an installed one. It prints what it freed.

Exit codes: 0 done, 2 usage error or no such folder.
"""

import argparse
import hashlib
import os
import shutil
import sys
import time
from pathlib import Path

# NOTE: smaller files save little and cost a hash each
MIN_SIZE = 64 * 1024


def newest_write(env: Path) -> float:
    """The newest mtime of any file in env, or of env itself when it is empty."""
    newest = env.stat().st_mtime
    for root, _, files in os.walk(env):
        for f in files:
            try:
                newest = max(newest, (Path(root) / f).lstat().st_mtime)
            except OSError:  # a file removed while walking
                continue
    return newest


def prune(env_dir: Path, days: float, now: float) -> list[Path]:
    """Remove the environments with no write in `days` days; returns them."""
    stale = [e for e in sorted(env_dir.glob("*/*/")) if now - newest_write(e) > days * 86400]
    for e in stale:
        shutil.rmtree(e)
    return stale


def digest(path: Path) -> str:
    """SHA-256 of the file's bytes, as hex."""
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def link_duplicates(env_dir: Path) -> int:
    """Hardlink identical regular files (same size, mode and SHA-256) to one copy; returns bytes freed."""
    by_size: dict[tuple[int, int], list[Path]] = {}
    seen: set[tuple[int, int]] = set()  # (device, inode): count each file once
    for root, _, files in os.walk(env_dir):
        for f in files:
            p = Path(root) / f
            st = p.lstat()
            if not p.is_file() or p.is_symlink() or st.st_size < MIN_SIZE or (st.st_dev, st.st_ino) in seen:
                continue
            seen.add((st.st_dev, st.st_ino))
            by_size.setdefault((st.st_size, st.st_mode), []).append(p)
    freed = 0
    for (size, _), paths in by_size.items():
        if len(paths) < 2:
            continue
        first: dict[str, Path] = {}
        for p in paths:
            keep = first.setdefault(digest(p), p)
            if keep is p:
                continue
            tmp = p.with_name(p.name + ".tidy-link")
            try:
                os.link(keep, tmp)
                tmp.replace(p)  # atomic: p is never missing
            except OSError:  # another file system, or a read-only file: keep the copy
                tmp.unlink(missing_ok=True)
                continue
            freed += size
    return freed


def main(argv: list[str] | None = None) -> int:
    """Prune, then link; see the module docstring."""
    parser = argparse.ArgumentParser(
        description=__doc__.split("\n\n")[0],
        epilog="example:\n  scripts/tidy_envs.py .asv/env --days 30\n\nexit codes: 0 done; 2 usage error",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        allow_abbrev=False,
    )
    parser.add_argument("env_dir", type=Path, help="asv's environment folder, such as .asv/env")
    parser.add_argument("--days", type=float, default=30, help="remove environments unused this long (default 30)")
    args = parser.parse_args(argv)
    if not args.env_dir.is_dir():
        parser.error(f"no folder {args.env_dir.as_posix()!r}")
    stale = prune(args.env_dir, args.days, time.time())
    freed = link_duplicates(args.env_dir)
    print(f"removed {len(stale)} environments unused for {args.days:g} days; hardlinks freed {freed / 2**30:.1f} GiB")
    for e in stale:
        print(f"  removed {e.relative_to(args.env_dir).as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
