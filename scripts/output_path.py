"""Check host output paths before touching folders writable by benchmark containers."""

from pathlib import Path


def output_path(path: Path) -> Path:
    """Reject a symlink at PATH or any existing ancestor, including dangling links."""
    absolute = path.absolute()
    for entry in (absolute, *absolute.parents):
        if entry.is_symlink():
            msg = f"Refusing output through a symlink: {entry}"
            raise ValueError(msg)
    return path
