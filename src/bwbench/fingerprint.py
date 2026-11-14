"""The environment a timing came from, as one JSON object: ``fingerprint()`` and ``problems()``.

Every result this project publishes carries one under the key ``"fingerprint"``: asv result
files (``scripts/fingerprints.py stamp``), the canary's nightly files (``scripts/canary.py``),
and any result written off the benchmark node. ``just results-commit`` refuses a new or changed
result without a valid one.

Fields (all present, ``null`` where this platform cannot tell):

- ``version``: 1, the shape of this object.
- ``os``, ``kernel``, ``arch``: ``platform.system()``, ``platform.release()``, ``platform.machine()``.
  In a container the kernel is the host's.
- ``cpu_model``: the CPU's brand string.
- ``core_type``: on Linux, ``"performance"`` or ``"efficiency"`` when every CPU this process may
  run on is of that type on a hybrid CPU, ``"mixed"`` when both, ``"uniform"`` on a CPU with one
  core type.
- ``smt``: whether simultaneous multithreading (Hyper-Threading) is on.
- ``governor``: Linux's cpufreq governor over the CPUs this process may run on, comma-joined
  when they differ.
- ``power_profile``: the energy-performance preference (what power-profiles-daemon sets on
  intel_pstate and amd-pstate), else the ACPI platform profile.
- ``python``: implementation and version of the interpreter that ran this, ``"CPython 3.12.7"``.
- ``blas``: conda's ``libblas`` build where there is one (it names the BLAS variant), else
  NumPy's build-time BLAS as ``"<name> <version>"``; ``null`` without NumPy.
- ``lock``: ``{"name": ..., "sha256": ...}`` of the lock file the environment was built from.
  An asv result must name one (``problems(fp, need_lock=True)``); a file without a lock, such
  as the canary's, may leave it ``null``.

The CPU numbers this process is pinned to are left out on purpose: they would name a private
slot. Standard library only, and Python 3.10 or newer, so any environment can run this file
directly: ``python -I fingerprint.py [LOCK]`` prints the object.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import subprocess
import sys
from pathlib import Path

VERSION = 1
# Each field's type when known; every field may also be None.
FIELDS: dict[str, type] = {
    "version": int,
    "os": str,
    "kernel": str,
    "arch": str,
    "cpu_model": str,
    "core_type": str,
    "smt": bool,
    "governor": str,
    "power_profile": str,
    "python": str,
    "blas": str,
    "lock": dict,
}
CPU = Path("/sys/devices/system/cpu")


def _read(path: Path) -> str | None:
    try:
        return path.read_text().strip() or None
    except OSError:
        return None


def _cpus(text: str) -> set[int]:
    """A Linux CPU list such as ``0-15,20`` as a set."""
    out: set[int] = set()
    for part in text.split(","):
        a, _, b = part.partition("-")
        out.update(range(int(a), int(b or a) + 1))
    return out


def _allowed() -> set[int]:
    return set(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else set()


def _per_cpu(name: str) -> str | None:
    """One cpufreq setting over the CPUs this process may run on, comma-joined when they differ."""
    values = {_read(CPU / f"cpu{n}/cpufreq/{name}") for n in _allowed()} - {None}
    return ",".join(sorted(v for v in values if v)) or None


def _sysctl(name: str) -> str | None:
    try:
        out = subprocess.run(["/usr/sbin/sysctl", "-n", name], capture_output=True, text=True, check=True, timeout=10)  # noqa: S603
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() or None


def _cpu_model() -> str | None:
    system = platform.system()
    if system == "Linux":
        for line in (_read(Path("/proc/cpuinfo")) or "").splitlines():
            key, _, value = line.partition(":")
            if key.strip() == "model name":
                return value.strip() or None
        return None
    if system == "Darwin":
        return _sysctl("machdep.cpu.brand_string")
    if sys.platform == "win32":  # not platform.system(): type checkers narrow on this
        import winreg  # noqa: PLC0415

        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as key:
                return str(winreg.QueryValueEx(key, "ProcessorNameString")[0]).strip() or None
        except OSError:
            return None
    return None


def _core_type() -> str | None:
    if platform.system() != "Linux":
        return None
    core, atom = _read(Path("/sys/devices/cpu_core/cpus")), _read(Path("/sys/devices/cpu_atom/cpus"))
    if core is None and atom is None:
        return "uniform"
    allowed = _allowed()
    # Linux can list only one of the two, as when every E-core is offline.
    kinds = {"performance" for _ in allowed & (_cpus(core) if core else set())} | {
        "efficiency" for _ in allowed & (_cpus(atom) if atom else set())
    }
    return kinds.pop() if len(kinds) == 1 else "mixed" if kinds else None


def _smt() -> bool | None:
    system = platform.system()
    if system == "Linux":
        active = _read(CPU / "smt/active")
        return None if active is None else active == "1"
    if system == "Darwin":
        physical, logical = _sysctl("hw.physicalcpu"), _sysctl("hw.logicalcpu")
        return None if physical is None or logical is None else physical != logical
    return None


def _power_profile() -> str | None:
    return _per_cpu("energy_performance_preference") or _read(Path("/sys/firmware/acpi/platform_profile"))


def _blas() -> str | None:
    conda = sorted(Path(sys.prefix, "conda-meta").glob("libblas-*.json"))
    if conda:
        return conda[0].stem
    try:
        import numpy as np  # noqa: PLC0415
    except ImportError:
        return None
    try:
        blas = np.show_config(mode="dicts")["Build Dependencies"]["blas"]
    except (AttributeError, KeyError, TypeError):  # NumPy before 1.26
        return None
    return " ".join(str(blas[k]) for k in ("name", "version") if blas.get(k)) or None


def fingerprint(lock: Path | None = None) -> dict:
    """The fingerprint of this process's machine and interpreter, with LOCK's checksum if given."""
    return {
        "version": VERSION,
        "os": platform.system() or None,
        "kernel": platform.release() or None,
        "arch": platform.machine() or None,
        "cpu_model": _cpu_model(),
        "core_type": _core_type(),
        "smt": _smt(),
        "governor": _per_cpu("scaling_governor"),
        "power_profile": _power_profile(),
        "python": f"{platform.python_implementation()} {platform.python_version()}",
        "blas": _blas(),
        "lock": {"name": lock.name, "sha256": hashlib.sha256(lock.read_bytes()).hexdigest()} if lock else None,
    }


def problems(fp: object, *, need_lock: bool = False) -> list[str]:
    """What makes FP not a fingerprint of this version: missing or unknown fields, wrong types.

    With NEED_LOCK, a ``null`` lock is a problem too: an asv result must say what environment ran it.
    """
    if not isinstance(fp, dict):
        return ["no fingerprint"]
    out = [f"missing field {k}" for k in FIELDS if k not in fp]
    out += [f"unknown field {k!r}" for k in fp if k not in FIELDS]
    for k, kind in FIELDS.items():
        value = fp.get(k)
        # bool is an int in Python, so version: true would pass isinstance(value, int).
        if value is not None and (not isinstance(value, kind) or (kind is int and isinstance(value, bool))):
            out.append(f"{k} is neither {kind.__name__} nor null")
    if fp.get("version") != VERSION:
        out.append(f"version is not {VERSION}")
    lock = fp.get("lock")
    if isinstance(lock, dict) and (
        set(lock) != {"name", "sha256"} or not all(isinstance(v, str) for v in lock.values())
    ):
        out.append("lock is not {name, sha256}")
    if need_lock and lock is None:
        out.append("no lock: the environment that ran it is unknown")
    return out


if __name__ == "__main__":
    if len(sys.argv) > 2 or (len(sys.argv) == 2 and sys.argv[1].startswith("-")):
        sys.stderr.write("usage: fingerprint.py [LOCK]\n")
        sys.exit(2)
    print(json.dumps(fingerprint(Path(sys.argv[1]) if len(sys.argv) == 2 else None)))  # noqa: T201
