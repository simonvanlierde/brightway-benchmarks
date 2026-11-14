#!/usr/bin/env python3
"""Put a fingerprint on asv result files, or check that results carry one.

``fingerprints.py stamp ENV_ROOT FILE...`` (asv.sh, in the box, after ``asv run``): for each
asv result FILE, find the environment under ENV_ROOT (``.asv/env/SUBJECT``) that ran it, run
``src/bwbench/fingerprint.py`` with that environment's Python and the lock file asv.sh wrote
for it beside FILE, and store the object under the file's ``"fingerprint"`` key. Files that
are not results (machine.json, benchmarks.json) are skipped.

``fingerprints.py check TREE`` (results-commit.sh): every JSON file staged as new or changed in
the git worktree TREE, other than asv's machine.json and benchmarks.json and the RO-Crate, must
carry a valid fingerprint (``bwbench.fingerprint.problems``). Files already committed are not
checked again: results from before the fingerprint stay as they are until a run rewrites them.

Exit codes: 0 done, 1 a file could not be stamped or lacks a valid fingerprint, 2 usage error.
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bwbench.fingerprint import problems  # noqa: E402

PROBE = ROOT / "src" / "bwbench" / "fingerprint.py"
NOT_RESULTS = {"machine.json", "benchmarks.json", "ro-crate-metadata.json"}


def env_key(tool: str, python: str, requirements: dict, env_vars: dict) -> str:
    """What asv names an environment by, as one comparable string."""
    return json.dumps([tool, python, requirements, env_vars], sort_keys=True)


def environments(root: Path) -> dict[str, Path]:
    """Each environment folder under ROOT by its key, from the asv-env-info.json asv leaves there."""
    out = {}
    for info in root.glob("*/asv-env-info.json"):
        d = json.loads(info.read_text())
        out[env_key(d["tool_name"], d["python"], d["requirements"], d["build_env_vars"])] = info.parent
    return out


def stamp(root: Path, files: list[Path]) -> int:
    """Stamp FILES with their environments' fingerprints; 1 if any could not be."""
    envs, done, status = environments(root), {}, 0
    for path in files:
        if path.name in NOT_RESULTS:
            continue
        data = json.loads(path.read_text())
        # asv names the result's environment <tool>-py<python>-...; its env_vars are build variables here.
        key = env_key(data["env_name"].split("-", 1)[0], data["python"], data["requirements"], data["env_vars"])
        env = envs.get(key)
        if env is None:
            print(f"fingerprints: {path}: no environment under {root} ran it", file=sys.stderr)
            status = 1
            continue
        if env not in done:
            locks = [path.parent / f"pylock.{env.name}.toml", path.parent / f"versions-{env.name}.txt"]
            lock = next((p for p in locks if p.is_file()), None)
            args = [str(env / "bin" / "python"), "-I", str(PROBE), *([str(lock)] if lock else [])]
            done[env] = json.loads(subprocess.run(args, capture_output=True, text=True, check=True).stdout)  # noqa: S603
        path.write_text(json.dumps(data | {"fingerprint": done[env]}))
    return status


def check(tree: Path) -> int:
    """1 if a result staged in TREE lacks a valid fingerprint, with each file and why on stderr."""
    git = shutil.which("git") or "git"
    staged = subprocess.run(  # noqa: S603
        [git, "-C", str(tree), "diff", "--cached", "--name-only", "--diff-filter=AM", "-z", "--", "*.json"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split("\0")
    bad = 0
    for name in filter(None, staged):
        if Path(name).name in NOT_RESULTS:
            continue
        try:
            found = problems(json.loads((tree / name).read_text()).get("fingerprint"))
        except (json.JSONDecodeError, AttributeError):
            found = ["not a JSON object"]
        if found:
            print(f"fingerprints: {name}: {'; '.join(found)}", file=sys.stderr)
            bad += 1
    if bad:
        print(
            f"fingerprints: {bad} result(s) without a valid fingerprint; rerun them with this asv.sh", file=sys.stderr
        )
    return 1 if bad else 0


def main(argv: list[str]) -> int:
    """Run the subcommand in ARGV."""
    if len(argv) >= 3 and argv[0] == "stamp":
        return stamp(Path(argv[1]), [Path(a) for a in argv[2:]])
    if len(argv) == 2 and argv[0] == "check":
        return check(Path(argv[1]))
    print("usage: fingerprints.py stamp ENV_ROOT FILE... | check TREE", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
