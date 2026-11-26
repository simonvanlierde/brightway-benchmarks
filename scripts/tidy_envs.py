#!/usr/bin/env python3
"""Keep asv's environments in ``.asv/env/`` small: drop stale ones, hardlink identical files.

asv builds one environment per subject and matrix entry and never removes one whose entry left
the config, and its environment type installs the matrix packages with pip, which copies every
file. So the folder only grows, about 300 MB per environment, most of it the same numpy, scipy
and pandas files.

``tidy_envs.py ENV_DIR [--days N]`` removes each environment (``ENV_DIR/<subject>/<hash>/``)
that asv has not used in N days (default 30), then replaces identical files across the rest
with hardlinks to one copy. Use is the access or modification time of the environment's
``asv-install-status.json``, which asv reads on every run and rewrites on every install; with
the file system's relatime, reads move the access time at least once a day. (File mtimes are no
use: asv installs nothing when the commit is already there, and a hardlink shares one mtime.)
Files are only compared, never imported or run, so it runs on the host. A hardlink is safe here:
pip and Python replace files (unlink, or write and rename) and never write into an installed
one. A subject whose asv lock (``.asv/<subject>.lock``, held by scripts/asv.sh during a run) is
taken is left alone, and a run asv.sh starts meanwhile fails at once instead of waiting.
``--dry-run`` reports without changing anything. It prints what it freed.

Exit codes: 0 done, 2 usage error or no such folder.
"""

import argparse
import fcntl
import hashlib
import os
import shutil
import stat
import sys
import time
from pathlib import Path

# NOTE: smaller files save little and cost a hash each
MIN_SIZE = 64 * 1024
TMP = ".tidy-link"
GONE = ".tidy-rm"


def lock_subjects(env_dir: Path) -> tuple[list[Path], list[str], list[int]]:
    """Each subject folder whose asv lock this run could take, the busy subjects, and the held locks."""
    free, busy, fds = [], [], []
    for subject in sorted(d for d in env_dir.iterdir() if d.is_dir() and not d.is_symlink()):
        fd = os.open(env_dir.parent / f"{subject.name}.lock", os.O_WRONLY | os.O_CREAT, 0o644)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(fd)
            busy.append(subject.name)
            continue
        fds.append(fd)
        free.append(subject)
    return free, busy, fds


def last_used(env: Path) -> float:
    """When asv last read or wrote env's install status, or env's own mtime when it has none."""
    try:
        st = (env / "asv-install-status.json").stat()
    except FileNotFoundError:
        return env.stat().st_mtime
    return max(st.st_atime, st.st_mtime)


def prune(subjects: list[Path], days: float, now: float, *, dry_run: bool = False) -> list[Path]:
    """Remove the environments asv has not used in `days` days; returns them."""
    for s in subjects:  # left by a run that was stopped mid-delete; asv no longer sees them
        for gone in s.glob(f"*{GONE}"):
            if not dry_run:
                shutil.rmtree(gone, ignore_errors=True)
    stale = [
        e
        for s in subjects
        for e in sorted(s.iterdir())
        if e.is_dir() and not e.is_symlink() and not e.name.endswith(GONE) and now - last_used(e) > days * 86400
    ]
    if not dry_run:
        for e in stale:
            # the rename is atomic, so asv never meets a half-deleted environment under its name
            gone = e.rename(e.with_name(e.name + GONE))
            shutil.rmtree(gone, ignore_errors=True)
    return stale


def digest(path: Path) -> str:
    """SHA-256 of the file's bytes, as hex."""
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def candidates(subjects: list[Path], *, dry_run: bool = False) -> dict[tuple[int, int], list[tuple[Path, int]]]:
    """Regular files of at least MIN_SIZE by (size, mode), each inode once, with its link count."""
    by_size: dict[tuple[int, int], list[tuple[Path, int]]] = {}
    seen: set[tuple[int, int]] = set()  # (device, inode)
    for subject in subjects:
        for root, _, files in os.walk(subject):
            for f in files:
                p = Path(root) / f
                try:
                    if f.endswith(TMP):  # left by a run that was killed between link and rename
                        if not dry_run:
                            p.unlink()
                        continue
                    st = p.lstat()
                except OSError:  # removed while walking
                    continue
                if not stat.S_ISREG(st.st_mode) or st.st_size < MIN_SIZE or (st.st_dev, st.st_ino) in seen:
                    continue
                seen.add((st.st_dev, st.st_ino))
                by_size.setdefault((st.st_size, st.st_mode), []).append((p, st.st_nlink))
    return by_size


def link_duplicates(subjects: list[Path], *, dry_run: bool = False) -> int:
    """Hardlink identical regular files (same size, mode and SHA-256) to one copy; returns bytes freed."""
    freed = 0
    for (size, _), paths in candidates(subjects, dry_run=dry_run).items():
        if len(paths) < 2:
            continue
        first: dict[str, Path] = {}
        for p, links in paths:
            try:
                keep = first.setdefault(digest(p), p)
            except OSError:
                continue
            if keep is p:
                continue
            if not dry_run:
                tmp = p.with_name(p.name + TMP)
                try:
                    os.link(keep, tmp)
                    tmp.replace(p)  # atomic: p is never missing
                except OSError:  # another file system, or a read-only file: keep the copy
                    tmp.unlink(missing_ok=True)
                    continue
            if links == 1:  # an inode shared with uv's cache or another copy frees nothing
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
    parser.add_argument("--dry-run", action="store_true", help="report what would go, change nothing")
    args = parser.parse_args(argv)
    if args.days <= 0:
        parser.error(f"--days must be above 0, got {args.days:g}: 0 would remove every environment")
    if not args.env_dir.is_dir():
        parser.error(f"no folder {args.env_dir.as_posix()!r}")
    subjects, busy, fds = lock_subjects(args.env_dir)
    try:
        stale = prune(subjects, args.days, time.time(), dry_run=args.dry_run)
        freed = link_duplicates(subjects, dry_run=args.dry_run)
    finally:
        for fd in fds:
            os.close(fd)
    verb, link_verb = ("would remove", "would free") if args.dry_run else ("removed", "freed")
    print(
        f"{verb} {len(stale)} environments unused for {args.days:g} days; hardlinks {link_verb} {freed / 2**30:.1f} GiB"
    )
    for e in stale:
        print(f"  {verb} {e.relative_to(args.env_dir).as_posix()}")
    for name in busy:
        print(f"  skipped {name}: asv holds its lock")
    return 0


if __name__ == "__main__":
    sys.exit(main())
