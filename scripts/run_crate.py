#!/usr/bin/env python3
"""Describe one machine's results folder as an RO-Crate: ``run_crate.py RESULTS_DIR/MACHINE``.

Writes ``ro-crate-metadata.json`` next to asv's result files and the ``pylock.<env>.toml``
files ``asv.sh`` leaves there: which files the folder holds, which bwbench commit and
generator produced them, and the profiles they used. Rerun after every run; it replaces the
file. RO-Crate 1.1: https://w3id.org/ro/crate/1.1
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


def commit() -> str | None:
    """The bwbench commit, or None outside a git checkout."""
    run = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True, check=False)  # noqa: S603, S607 - fixed git command
    return run.stdout.strip() or None


def crate(folder: Path) -> dict:
    """The RO-Crate metadata for ``folder``."""
    files = sorted(p for p in folder.iterdir() if p.is_file() and p.name != "ro-crate-metadata.json")
    kinds = {".json": "asv result", ".toml": "PEP 751 lock file of one asv environment", ".txt": "pip freeze"}
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
        "@context": "https://w3id.org/ro/crate/1.1/context",
        "@graph": [
            {
                "@id": "ro-crate-metadata.json",
                "@type": "CreativeWork",
                "conformsTo": {"@id": "https://w3id.org/ro/crate/1.1"},
                "about": {"@id": "./"},
            },
            {
                "@id": "./",
                "@type": "Dataset",
                "name": f"brightway-benchmarks results on {folder.name}",
                "datePublished": datetime.now(UTC).date().isoformat(),
                "license": {"@id": "https://spdx.org/licenses/BSD-3-Clause"},
                "hasPart": [{"@id": f.name} for f in files],
                "mentions": {"@id": "#run"},
            },
            {
                "@id": "#run",
                "@type": "CreateAction",
                "name": "asv run",
                "instrument": {"@id": software["@id"]},
                "object": [{"@id": p["@id"]} for p in profiles],
                "result": [{"@id": f.name} for f in files],
            },
            software,
            *profiles,
            *[{"@id": f.name, "@type": "File", "description": kinds.get(f.suffix, "")} for f in files],
        ],
    }


def main() -> None:
    """Write the crate for the folder named on the command line."""
    folder = Path(sys.argv[1])
    (folder / "ro-crate-metadata.json").write_text(json.dumps(crate(folder), indent=2) + "\n")


if __name__ == "__main__":
    main()
