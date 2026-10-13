#!/usr/bin/env python3
"""Describe benchmark results as an RO-Crate: ``run_crate.py RESULTS_ROOT``.

Writes ``ro-crate-metadata.json`` into the results root (``results/`` or ``.asv/smoke/``),
above each subject's asv folder and its machine folders, which hold asv's result files and
the ``pylock.*.toml`` files ``asv.sh`` leaves there. It names the
files, the bwbench commit and generator version, and the digest of every registered profile.
Rerun after every run; it replaces the file. RO-Crate 1.3: https://w3id.org/ro/crate/1.3
"""

import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bwbench.synth import GENERATOR_VERSION, PROFILES  # noqa: E402

REPO = "https://github.com/simonvanlierde/brightway-benchmarks"
LICENSE = "https://spdx.org/licenses/BSD-3-Clause"


def commit() -> str | None:
    """The bwbench commit, or None outside a git checkout."""
    run = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True, check=False)  # noqa: S603, S607 - fixed git command
    return run.stdout.strip() or None


def crate(folder: Path) -> dict:
    """The RO-Crate metadata for every file under the results root ``folder``."""
    files = sorted(p for p in folder.rglob("*") if p.is_file() and p.name != "ro-crate-metadata.json")
    ids = [p.relative_to(folder).as_posix() for p in files]
    kinds = {".json": "asv result", ".toml": "PEP 751 lock file of one asv environment", ".txt": "pip freeze"}
    named = {"machine.json": "asv machine description", "benchmarks.json": "asv benchmark list"}
    sha = commit()
    software = {
        "@id": f"{REPO}/tree/{sha}" if sha else REPO,
        "@type": "SoftwareSourceCode",
        "name": "bwbench",
        "codeRepository": REPO,
        "version": sha or "unknown",
        "description": f"generator version {GENERATOR_VERSION}",
    }
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
                "mentions": {"@id": "#run"},
            },
            {"@id": LICENSE, "@type": "CreativeWork", "name": "BSD 3-Clause License"},
            {
                "@id": "#run",
                "@type": "CreateAction",
                "name": "asv run",
                "instrument": {"@id": software["@id"]},
                "object": [{"@id": p["@id"]} for p in profiles],
                "result": [{"@id": i} for i in ids],
            },
            software,
            *profiles,
            *[
                {"@id": i, "@type": "File", "description": named.get(f.name, kinds.get(f.suffix, ""))}
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
