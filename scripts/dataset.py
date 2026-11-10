"""The synthetic inputs as a dataset for Zenodo: ``dataset.py OUT [PROFILE ...]``.

For each generated profile (all of them by default) at seed 0 and the current
``GENERATOR_VERSION``, writes into OUT:

- ``<profile>-matrices.zip``: the bw_processing datapackages the benchmarks load, with
  ``reference.json`` (the reference scores) and ``scale.npy`` (each product's unit);
- ``<profile>-ecospold2.zip``: the same system as an ecoSpold2 release, one file per product;
- ``README.md`` (the dataset card), ``metadata.json`` and ``SHA256SUMS`` over every other file.

Profiles read from a real archive (``synth.ARCHIVES``) are refused: BAFU's terms forbid
redistribution, and USEEIO (public domain) is not generator output. Every ecoSpold2 file is
scanned before it is zipped (``licensed_hits``). What was left out goes to ``OUT-review/``,
outside the archive, when anything was. Nothing is uploaded. ``just dataset`` runs this in the benchmark box,
which has bw_processing.
"""

# First, so the BLAS thread pin lands before numpy loads (bwbench warns otherwise).
import bwbench  # noqa: F401, I001
import argparse
import json
import os
import re
import shutil
import sys
import tempfile
import uuid
import zipfile
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from bwbench import ecospold, synth
from bwbench.matrices import write_datapackages
from bwbench.shapes import PROFILES, Profile
from bwbench.useeio import sha256_of

LICENSE = "CC-BY-4.0"
SEED = 0  # the seed every benchmark uses
SPARE_FLOWS = 100  # padding flows past a profile's own, which write_ecospold fills to ecoinvent's mean count
ZENODO_FILES, ZENODO_BYTES = 100, 50 * 10**9  # per record
UUID = re.compile(rb"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
# The ecoSpold2 format's own namespace: a format name, not data.
NAMESPACE_URL = b"http://www.EcoInvent.org/EcoSpold02"
# The two unit ids the writer's templates use (kg, dimensionless). bw2io reads the unit's name.
LICENSED_NAME = b"ecoinvent"
UNIT_IDS = {b"487df68b-4994-4027-8fdc-a4dc298257b7", b"577e1a2c-4c2b-4d1e-9a3f-ff0d8f8b6a10"}


def flow_ids(p: Profile) -> list[str]:
    """Elementary flow ``j``'s UUID: ``uuid5(ecospold.NAMESPACE, "flow j")``, never a real database's."""
    return [str(uuid.uuid5(ecospold.NAMESPACE, f"flow {j}")) for j in range(p.flows + SPARE_FLOWS)]


def refused(names: list[str]) -> dict[str, str]:
    """Profiles that must not ship, with the rule that leaves each out."""
    out = {}
    for name in names:
        if name not in PROFILES:
            out[name] = "not a registered profile"
        elif PROFILES[name].builder in synth.ARCHIVES:
            out[name] = f"read from the {PROFILES[name].target} archive, not generated"
    return out


def licensed_hits(text: bytes) -> list[str]:
    """What in one ecoSpold2 file could come from a licensed database; empty means clean.

    A UUID passes only as a name-based (version 5) UUID, which the writer derives from its own
    namespace, or as one of ``UNIT_IDS``. The ids in ecoinvent and its biosphere are random
    (version 4). "ecoinvent" may appear only in the format's namespace.
    """
    hits = [
        f"UUID {u.decode()}" for u in UUID.findall(text) if uuid.UUID(u.decode()).version != 5 and u not in UNIT_IDS
    ]
    if LICENSED_NAME in text.replace(NAMESPACE_URL, b"").lower():
        hits.append("the word ecoinvent outside the format namespace")
    return hits


def zip_folder(folder: Path, dest: Path, *, scan: bool) -> None:
    """Zip ``folder``'s files under their relative paths; with ``scan``, refuse a file with licensed hits."""
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for f in sorted(p for p in folder.rglob("*") if p.is_file()):
            data = f.read_bytes()
            if scan and (hits := licensed_hits(data)):
                msg = f"{f.name}: {', '.join(hits[:3])}"
                raise ValueError(msg)
            z.writestr(f.relative_to(folder).as_posix(), data)


def write_manifest(out: Path) -> list[dict]:
    """Write ``SHA256SUMS`` (``sha256sum -b`` format) over every file in ``out`` and return the entries."""
    files = [
        {"path": f.relative_to(out).as_posix(), "bytes": f.stat().st_size, "sha256": sha256_of(f)}
        for f in sorted(out.rglob("*"))
        if f.is_file() and f.name != "SHA256SUMS"
    ]
    (out / "SHA256SUMS").write_text("".join(f"{e['sha256']} *{e['path']}\n" for e in files))
    return files


def check_zenodo(files: list[dict]) -> None:
    """Refuse an archive over one Zenodo record's file count or size."""
    count, size = len(files) + 1, sum(e["bytes"] for e in files)  # + SHA256SUMS
    if count > ZENODO_FILES or size > ZENODO_BYTES:
        msg = f"{count} files, {size / 1e9:.1f} GB: over Zenodo's {ZENODO_FILES} files or {ZENODO_BYTES / 1e9:.0f} GB"
        raise ValueError(msg)


def card(profiles: dict[str, dict], commit: str) -> str:
    """The dataset card: Hugging Face front matter, then the Datasheets for Datasets questions."""
    rows = "\n".join(
        f"| `{n}` | {p['products']:,} | {p['flows']:,} | {p['entries']:,} | {p['builder']} |"
        for n, p in profiles.items()
    )
    total = sum(p["products"] for p in profiles.values())
    size = (
        "n<1K" if total < 1_000 else "1K<n<10K" if total < 10_000 else "10K<n<100K" if total < 100_000 else "100K<n<1M"
    )
    return f"""---
license: cc-by-4.0
language:
  - en
size_categories:
  - {size}
tags:
  - life-cycle-assessment
  - sparse-matrices
  - benchmark
  - synthetic
---

# Synthetic LCA systems, generator version {synth.GENERATOR_VERSION}

The seeded synthetic life cycle inventory systems that
[brightway-benchmarks](https://github.com/simonvanlierde/brightway-benchmarks) times the Brightway
LCA stack on, at commit `{commit}`. Each system comes as bw_processing datapackages and as an
ecoSpold2 release, so it can be used without running the generator.

| Profile | Products | Flows | Technosphere inputs | Builder |
| --- | --- | --- | --- | --- |
{rows}

## Motivation

Real LCI databases that set solver workloads, such as ecoinvent, cannot be redistributed. These
systems give the same kind of matrices to anyone: the `ecoinvent` profile has the size, degree
distributions, loops, signs and sparse-LU fill of ecoinvent 3.12 cut-off, measured as aggregate
statistics only (`docs/generator-calibration.md` in the repository).

## Composition

Per profile, at seed {SEED}:

- `<profile>-matrices.zip`: `inventory/` (technosphere and biosphere) and `method-<i>/` (one
  characterization each) as bw_processing datapackages; `reference.json` with the profile's
  fields and the scores of one unit of products 0 to 29 per method, from a Neumann series that
  shares no code with any solver; `scale.npy`, each product's signed unit.
- `<profile>-ecospold2.zip`: `datasets/`, one `.spold` file per product, with the elements bw2io's
  `Ecospold2DataExtractor` reads, padded to an ecoinvent 3.12 file's mean size with placeholder
  text. There is no `MasterData/`.

Product `i` is "process i" making "product i". Elementary flow `j` has the UUID
`uuid5({ecospold.NAMESPACE}, "flow j")`; flows from the profile's flow count up pad each dataset
with amounts below 1e-6. Import with a biosphere database holding these UUIDs. Nothing is missing:
every product has a production amount of 1.

## Collection process

Generated by `bwbench.synth.system(profile, seed={SEED})` from numpy's seeded generator: the same
arguments give the same arrays on every machine. No person or real process is described.

## Preprocessing

None. Amounts are written as generated (float64 in the arrays; the datapackages hold what
bw_processing stores).

## Uses

Timing and testing LCA software: matrix building, factorization, Monte Carlo, imports. The
systems are not an inventory of anything; their scores mean nothing environmentally.

## Known limits

Only the `ecoinvent` profile is calibrated. The others scale it (`mc100k`, `regional`) or use the
earlier random builder (`exiobase`, `stress-random`), whose LU fill is far above a real database's.
Input magnitudes are less dispersed than ecoinvent's.

## Distribution

{LICENSE}. `SHA256SUMS` holds the checksum of each file; `metadata.json` holds every profile's
fields. Each generator version is a new version of this record.

## Maintenance

Simon van Lierde, through the repository's issues. A change to the generator bumps
`GENERATOR_VERSION` and gives a new dataset version.
"""


def build(out: Path, names: list[str]) -> dict:
    """Write the dataset to ``out`` (which must not exist) and return its metadata.

    It is built in ``out.partial`` and renamed at the end, so a failed or killed run leaves no
    ``out`` for the written-once guard to refuse; the next run clears the partial folder.
    """
    final, out = out, out.with_name(out.name + ".partial")
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    try:
        meta = _build(out, names)
    except BaseException:
        shutil.rmtree(out, ignore_errors=True)
        raise
    out.rename(final)
    return meta


def _build(out: Path, names: list[str]) -> dict:
    commit = os.environ.get("BWBENCH_COMMIT") or "unknown"
    profiles = {}
    for name in names:
        s = synth.system(name, seed=SEED)
        # Inside OUT's partial folder, not the box's /tmp: unzipped, `regional`'s ecoSpold2 files take about 34 GB.
        with tempfile.TemporaryDirectory(prefix=f".{name}-", dir=out) as tmp:
            write_datapackages(s, Path(tmp) / "matrices")
            zip_folder(Path(tmp) / "matrices", out / f"{name}-matrices.zip", scan=False)
            ecospold.write_ecospold(s, Path(tmp) / "ecospold2", flow_ids(s.profile))
            zip_folder(Path(tmp) / "ecospold2", out / f"{name}-ecospold2.zip", scan=True)
        profiles[name] = asdict(s.profile) | {"digest": s.profile.digest(), "entries": int(s.tech_flip.sum())}
        print(f"{name}: written", file=sys.stderr)
    (out / "README.md").write_text(card(profiles, commit))
    meta = {
        "title": f"Synthetic LCA systems, generator version {synth.GENERATOR_VERSION}",
        "generator_version": synth.GENERATOR_VERSION,
        "commit": commit,
        "created": datetime.now(UTC).isoformat(timespec="seconds"),
        "license": LICENSE,
        "seed": SEED,
        "flow_uuid_namespace": str(ecospold.NAMESPACE),
        "profiles": profiles,
    }
    (out / "metadata.json").write_text(json.dumps(meta, indent=2) + "\n")
    meta["files"] = write_manifest(out)  # the manifest cannot list a file that holds it
    check_zenodo(meta["files"])
    return meta


def main(argv: list[str] | None = None) -> int:
    """Refuse what may not ship, record it in OUT-review/, then build OUT."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("out", type=Path)
    parser.add_argument("profiles", nargs="*", default=list(PROFILES))
    args = parser.parse_args(argv)
    if args.out.exists():
        parser.error(f"{args.out} exists: a dataset version is written once")
    left_out = refused(args.profiles)
    if left_out:
        review = args.out.with_name(args.out.name + "-review")
        shutil.rmtree(review, ignore_errors=True)
        review.mkdir(parents=True)
        (review / "excluded.json").write_text(json.dumps(left_out, indent=2) + "\n")
    for name, why in left_out.items():
        print(f"{name}: left out, {why}", file=sys.stderr)
    build(args.out, [n for n in args.profiles if n not in left_out])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
