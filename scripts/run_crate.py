#!/usr/bin/env python3
"""Describe benchmark results as an RO-Crate: ``run_crate.py RESULTS_ROOT``.

Writes ``ro-crate-metadata.json`` into the results root (``results/`` or ``.asv/smoke/``),
above each subject's asv folder and its machine folders, which hold asv's result files and
the ``pylock.*.toml`` files ``asv.sh`` leaves there. It names the files and the digest of
every registered profile. Each file is credited to the bwbench commit and generator version in
the newest ``bwbench-run-*.txt`` record (written by ``asv.sh``) that lists its checksum, or to an
unknown commit when none does. Rerun after every run; it replaces the file. RO-Crate 1.3: https://w3id.org/ro/crate/1.3
"""

import hashlib
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bwbench.synth import PROFILES  # noqa: E402

REPO = "https://github.com/simonvanlierde/brightway-benchmarks"
LICENSE = "https://spdx.org/licenses/BSD-3-Clause"


def writers(folder: Path) -> dict[str | tuple[str, str], tuple[str, str]]:
    """The (commit, generator version) of the newest run that wrote each file.

    Keyed by (sha256, crate id) and by sha256 alone: the first tells apart files with the same
    content in two subjects (machine.json), the second a file whose recorded path names no subject.
    Record names start with the time of the run, so sorting by name puts the newest last.
    """
    found: dict[str | tuple[str, str], tuple[str, str]] = {}
    for record in sorted(folder.rglob("bwbench-run-*.txt"), key=lambda p: p.name):
        lines = record.read_text().splitlines()
        head = dict(line.split(" ", 1) for line in lines if line.startswith(("commit ", "generator ")))
        run = (head.get("commit", "unknown"), head.get("generator", ""))
        subject = record.relative_to(folder).parts[0]  # asv.sh writes it in <subject>/<machine>/
        for line in lines:
            if line[64:66] != "  ":  # sha256sum's format
                continue
            sha, parts = line[:64], Path(os.path.normpath(line[66:])).parts
            found[sha] = run
            if subject in parts:
                start = len(parts) - 1 - parts[::-1].index(subject)
                found[sha, "/".join(parts[start:])] = run
        found[hashlib.sha256(record.read_bytes()).hexdigest()] = run
    return found


def software(sha: str, generator: str) -> dict:
    """The bwbench code at commit ``sha``; at the bare repository when it is unknown."""
    known = sha != "unknown"
    return {
        "@id": f"{REPO}/tree/{sha}" if known else REPO,
        "@type": "SoftwareSourceCode",
        "name": "bwbench",
        "codeRepository": REPO,
        "version": sha,
        **({"description": f"generator version {generator}"} if generator else {}),
    }


def crate(folder: Path) -> dict:
    """The RO-Crate metadata for every file under the results root ``folder``."""
    # Hidden files are not results: the .git file of the results branch's worktree, for one.
    files = sorted(
        p
        for p in folder.rglob("*")
        if p.is_file()
        and p.name != "ro-crate-metadata.json"
        and not any(part.startswith(".") for part in p.relative_to(folder).parts)
    )
    ids = [p.relative_to(folder).as_posix() for p in files]
    kinds = {".json": "asv result", ".toml": "PEP 751 lock file of one asv environment", ".txt": "pip freeze"}
    record = "which bwbench commit wrote which file, by sha256"
    named = {"machine.json": "asv machine description", "benchmarks.json": "asv benchmark list"}
    known = writers(folder)
    runs: dict[str, tuple[str, list[str]]] = {}  # commit: (generator version, files it wrote)
    for i, f in zip(ids, files, strict=True):
        digest = hashlib.sha256(f.read_bytes()).hexdigest()
        sha, generator = known.get((digest, i)) or known.get(digest, ("unknown", ""))
        runs.setdefault(sha, (generator, []))[1].append(i)
    code = [software(sha, generator) for sha, (generator, _) in runs.items()]
    profiles = [
        {"@id": f"#profile-{name}", "@type": "PropertyValue", "name": name, "value": p.digest()}
        for name, p in PROFILES.items()
    ]
    return {
        "@context": "https://w3id.org/ro/crate/1.3/context",
        "@graph": [
            {
                "@id": "ro-crate-metadata.json",
                "@type": "CreativeWork",
                "conformsTo": {"@id": "https://w3id.org/ro/crate/1.3"},
                "about": {"@id": "./"},
            },
            {
                "@id": "./",
                "@type": "Dataset",
                "name": "brightway-benchmarks results",
                "description": "asv timings of the Brightway stack on seeded synthetic LCA systems, with lock files.",
                "datePublished": datetime.now(UTC).date().isoformat(),
                "license": {"@id": LICENSE},
                "hasPart": [{"@id": i} for i in ids],
                "mentions": [{"@id": f"#run-{sha}"} for sha in runs],
            },
            {"@id": LICENSE, "@type": "CreativeWork", "name": "BSD 3-Clause License"},
            *[
                {
                    "@id": f"#run-{sha}",
                    "@type": "CreateAction",
                    "name": "asv run",
                    "instrument": {"@id": c["@id"]},
                    "object": [{"@id": p["@id"]} for p in profiles],
                    "result": [{"@id": i} for i in written],
                }
                for (sha, (_, written)), c in zip(runs.items(), code, strict=True)
            ],
            *code,
            *profiles,
            *[
                {
                    "@id": i,
                    "@type": "File",
                    "description": record
                    if f.name.startswith("bwbench-run-")
                    else named.get(f.name, kinds.get(f.suffix, "")),
                }
                for i, f in zip(ids, files, strict=True)
            ],
        ],
    }


def main() -> None:
    """Write the crate for the folder named on the command line."""
    folder = Path(sys.argv[1])
    (folder / "ro-crate-metadata.json").write_text(json.dumps(crate(folder), indent=2) + "\n")


if __name__ == "__main__":
    main()
