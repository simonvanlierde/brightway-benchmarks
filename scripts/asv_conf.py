#!/usr/bin/env python3
"""What the shell scripts read from asv/SUBJECT.json: ``asv_conf.py COMMAND SUBJECT [MACHINE]``.

Run from the repository root, with the standard library only (the box's python3, a CI runner's).

- ``conf SUBJECT MACHINE``: write the config asv reads to .asv/.SUBJECT.local.json and print the
  stack hash and the results folder (scripts/asv.sh). ``BWBENCH_SOLVERS`` picks the environments.
- ``stack-in SUBJECT``: the requirements the fixed stack resolves from (scripts/stack.sh).
- ``drop SUBJECT``: the packages the fixed stack leaves out (scripts/stack.sh).
- ``pins SUBJECT``: the pins asv installs beside the stack, space-separated (scripts/codspeed-venv.sh).
- ``repo SUBJECT``: the upstream repository asv clones (``just site``).
"""

import hashlib
import json
import os
import platform
import sys
from pathlib import Path

SOLVERS = ("superlu", "pypardiso", "umfpack", "klu", "umfpack-T")
X86_ONLY = ("pypardiso", "klu")
# The asv requirement that makes an environment a solver's. A patched solver's entry names its own
# (BWBENCH_SOLVER in its env) and installs the library it patches in (umfpack-T: scikit-umfpack).
SOLVER_OF = {"pypardiso": "pypardiso", "scikit-umfpack": "umfpack"}
# bw2calc's suite never imports bw2data, and bw2calc 2.0 to 2.2 fail to import beside bw2data 4.5
# or later (they compare its string version with a tuple).
UNUSED = {"bw2calc": {"bw2data"}}
OUT_OF_RESULTS = ("smoke", "noise", "stack")  # machines whose results stay under .asv/, off the site


def load(subject: str) -> dict:
    """asv/SUBJECT.json."""
    return json.loads(Path(f"asv/{subject}.json").read_text())


def stack_hash(subject: str) -> str:
    """The first 8 hex digits of asv/SUBJECT.stack.txt's SHA-256, as environment names carry it."""
    return hashlib.sha256(Path(f"asv/{subject}.stack.txt").read_bytes()).hexdigest()[:8]


def conf(subject: str, machine: str, solvers: str, arch: str) -> tuple[dict, str]:
    """The config asv reads for ``solvers`` (comma-separated) on ``arch``, and its stack hash."""
    data = load(subject)
    wanted = solvers.split(",")
    unknown = set(wanted) - set(SOLVERS)
    if unknown or not wanted:
        takes = f"{', '.join(SOLVERS[:-1])} and {SOLVERS[-1]}"
        msg = f"asv.sh: BWBENCH_SOLVERS takes {takes}, not {','.join(sorted(unknown))}"
        raise SystemExit(msg)
    for x86_only in X86_ONLY:
        if x86_only in wanted and arch != "x86_64":
            msg = f"asv.sh: {x86_only} has wheels for x86_64 only"
            raise SystemExit(msg)
    # asv names an environment after its matrix, not after the stack file it installs. A hash
    # of the stack in the name rebuilds the environments when the stack changes, and keeps a
    # resumed run from counting results made on the old stack as done.
    stack = stack_hash(subject)
    data["matrix"]["env"] = {"BWBENCH_STACK": [stack]}
    # Added to an entry's own env, not in place of it: the env is part of the environment's
    # name, so the entries without one keep the names their results are filed under.
    for e in data.get("include", []):
        e.setdefault("env", {})["BWBENCH_STACK"] = stack
    if data.get("include"):
        data["include"] = [e for e in data["include"] if solvers_of(e) <= set(wanted)]
        if "superlu" not in wanted:
            data["exclude"] = [{"python": ".*"}]  # asv excludes from the matrix only, never an include
    if machine in OUT_OF_RESULTS:
        data["results_dir"] = f"../.asv/{machine}/{subject}"
    return data, stack


def solvers_of(entry: dict) -> set[str]:
    """The solvers an ``include`` entry's environment stands for."""
    if "BWBENCH_SOLVER" in entry["env"]:
        return {entry["env"]["BWBENCH_SOLVER"]}
    return {SOLVER_OF[k] for k in entry["req"] if k in SOLVER_OF}


def stack_in(subject: str) -> list[str]:
    """The subject's latest release and the config's matrix pins, one requirement each."""
    data = load(subject)
    latest = Path(f"asv/{subject}.hashes").read_text().split()[-1].removeprefix("v")
    pins = [
        v[0] if v[0].startswith("git+") else f"{k.removeprefix('pip+')}=={v[0]}"
        for k, v in data["matrix"]["req"].items()
    ]
    return [f"{subject}=={latest}", *pins]


def drop(subject: str) -> list[str]:
    """What the stack leaves out: the subject, what the config varies, and what the suite never imports."""
    data = load(subject)
    varied = {k for k, v in data["matrix"]["req"].items() if len(v) > 1}
    varied |= {k for env in data.get("include", []) for k in env["req"]}
    names = {subject, *varied, *UNUSED.get(subject, set())} - {"numpy", "scipy", "pip+asv_runner"}
    return sorted(n.removeprefix("pip+").replace("_", "-").lower() for n in names)


def pins(subject: str) -> list[str]:
    """The matrix pins asv installs, and the pinned extras its install_command adds (bw2calc 3.x's threadpoolctl)."""
    data = load(subject)
    found = [f"{k}=={v[0]}" for k, v in data["matrix"]["req"].items() if not k.startswith("pip+")]
    return found + [w for c in data.get("install_command", []) for w in c.split() if "==" in w]


def main(argv: list[str]) -> None:
    """Run one command; see the module docstring."""
    match argv:
        case ["conf", subject, machine]:
            data, stack = conf(subject, machine, os.environ["BWBENCH_SOLVERS"], platform.machine())
            Path(f".asv/.{subject}.local.json").write_text(json.dumps(data, indent=2))
            print(stack, f".asv/{data['results_dir']}")
        case ["stack-in", subject]:
            print("\n".join(stack_in(subject)))
        case ["drop", subject]:
            print("\n".join(drop(subject)))
        case ["pins", subject]:
            print(" ".join(pins(subject)))
        case ["repo", subject]:
            print(load(subject)["repo"])
        case _:
            raise SystemExit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
