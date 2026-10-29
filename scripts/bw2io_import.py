r"""Time and peak memory of an ecoinvent import with bw2io's importers, per database size.

    just bw2io-import RELEASE_FOLDER SIZES     # a licensed release, SIZES like 3000,9000,all
    just bw2io-import synthetic SIZES          # the generated release, SIZES like smoke,ecoinvent

The recipe runs this script with bw2io 0.9.17 and bw2data 4.8. A licensed ecoinvent release
(the folder holding ``datasets/`` and ``MasterData/``) is mounted read-only at /ecoinvent into
a plain ``docker run`` of the box image, as ``scripts/solver_factorize.py`` describes: ``box.sh``
mounts only this repo. ``synthetic`` writes the profile's system as ecoSpold2 files first
(``bwbench.ecospold``, untimed) and needs no licence.

Runs the LCI half of ``bw2io.import_ecoinvent_release``: core migrations, the biosphere,
``SingleOutputEcospold2Importer``, ``apply_strategies``, ``write_database``. LCIA is left out.
The biosphere is the release's ``MasterData/ElementaryExchanges.xml``, or for the synthetic
release ``bw2io.create_default_biosphere3()``, whose flow UUIDs the synthetic files use.
Each import runs in a fresh interpreter with a fresh project folder, and prints one JSON line
of aggregates only: wall and CPU seconds and peak RSS per step, and dataset, exchange and
unlinked counts. Never a dataset's name or amount.

A numbered size is a seeded random sample of the release's dataset files, the same for every
bw2io release. bw2io's ``delete_exchanges_missing_activity`` deletes inputs from outside the
sample, so a subset writes fewer exchanges per dataset; the full release must link. The
synthetic release must link at every size and import exactly the system's exchanges.

    python scripts/bw2io_import.py RELEASE SIZES [PYTHON...]   # driver; default PYTHON: this one
    python scripts/bw2io_import.py --one RELEASE SIZE          # one import, in this interpreter

With PROFILE_WRITE=1, ``--one`` also prints a cProfile of ``write_database`` to stderr (top 40
by cumulative time, function names only). BWBENCH_ROUNDS repeats the whole set.
"""

import json
import os
import random
import re
import resource
import subprocess
import sys
import tempfile
import time
from importlib.metadata import version
from importlib.util import find_spec
from pathlib import Path

# The driver starts each import with `python -I`, which ignores PYTHONPATH.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
ROUNDS = int(os.environ.get("BWBENCH_ROUNDS", "1"))


def usage() -> dict:
    """CPU seconds so far and peak RSS of this process and of its largest finished child."""
    s, c = resource.getrusage(resource.RUSAGE_SELF), resource.getrusage(resource.RUSAGE_CHILDREN)
    return {
        "cpu": s.ru_utime + s.ru_stime + c.ru_utime + c.ru_stime,
        "rss_mb": round(s.ru_maxrss / 1024),  # Linux reports KiB
        "child_rss_mb": round(c.ru_maxrss / 1024),  # largest waited-for worker (use_mp extract)
    }


def subset(release: Path, size: str, root: Path) -> Path:
    """A folder laid out like a release (datasets/ beside MasterData/) holding SIZE dataset files."""
    if size == "all":
        return release
    files = sorted((release / "datasets").glob("*.spold"))
    (root / "datasets").mkdir(parents=True)
    (root / "MasterData").symlink_to(release / "MasterData")
    for f in random.Random(0).sample(files, int(size)):  # noqa: S311 - a seeded sample, not a secret
        (root / "datasets" / f.name).symlink_to(f)
    return root


def biosphere3_flows() -> list[str]:
    """The flow UUIDs ``create_default_biosphere3`` writes, in file order, read without importing bw2io."""
    spec = find_spec("bw2io")
    if spec is None or not spec.submodule_search_locations:
        msg = "bw2io is not installed"
        raise ImportError(msg)
    xml = Path(spec.submodule_search_locations[0], "data", "lci", "ecoinvent elementary flows 3.9.xml")
    return re.findall(r'<elementaryExchange[^>]*\sid="([^"]+)"', xml.read_text(encoding="utf-8"))


def synthetic(size: str, root: Path) -> tuple[Path, dict]:
    """Write profile SIZE's system as a release under ``root``; returns it and the expected counts."""
    from bwbench.ecospold import write_ecospold  # noqa: PLC0415
    from bwbench.synth import system  # noqa: PLC0415

    s = system(size)
    expect = {"datasets": s.profile.products, "unlinked": 0}
    return root, expect | {"exchanges": write_ecospold(s, root, biosphere3_flows())}


def one(release: str, size: str) -> dict:  # noqa: PLR0915 - one import, step by step
    """Import SIZE of RELEASE in a fresh project; returns the timings and counts."""
    out: dict = {"size": size}
    with tempfile.TemporaryDirectory(prefix="bw2io-import-") as tmp:
        os.environ["BRIGHTWAY2_DIR"] = f"{tmp}/bw"  # before bw2data loads
        Path(os.environ["BRIGHTWAY2_DIR"]).mkdir()
        expect = None
        if release == "synthetic":
            t = time.perf_counter()
            folder, expect = synthetic(size, Path(tmp) / "release")
            out["synthetic_release_s"] = round(time.perf_counter() - t, 2)  # not part of the total
        else:
            folder = subset(Path(release), size, Path(tmp) / "release")
        last = (time.perf_counter(), usage()["cpu"])

        def lap(name: str) -> None:
            nonlocal last
            now, u = time.perf_counter(), usage()
            out[name] = {
                "wall": round(now - last[0], 2),
                "cpu": round(u["cpu"] - last[1], 2),
                "rss_mb": u["rss_mb"],
                "child_rss_mb": u["child_rss_mb"],
            }
            last = (now, u["cpu"])

        import bw2data as bd  # noqa: PLC0415
        import bw2io as bi  # noqa: PLC0415
        from bw2io.importers import Ecospold2BiosphereImporter, SingleOutputEcospold2Importer  # noqa: PLC0415

        out["bw2io"], out["bw2data"] = version("bw2io"), version("bw2data")
        bd.projects.set_current("bw2io-import")
        lap("import")
        if not len(bi.migrations):
            bi.create_core_migrations()
        lap("migrations")
        flows = folder / "MasterData" / "ElementaryExchanges.xml"
        if flows.exists():
            bio = "ecoinvent-biosphere"
            eb = Ecospold2BiosphereImporter(name=bio, filepath=flows)
            eb.apply_strategies()
            if not eb.all_linked:
                msg = "biosphere has unlinked flows"
                raise ValueError(msg)
            eb.write_database(overwrite=False)
        else:
            bio = "biosphere3"
            bi.create_default_biosphere3()
        bd.preferences["biosphere_database"] = bio
        lap("biosphere")
        soup = SingleOutputEcospold2Importer(
            dirpath=str(folder / "datasets"), db_name="ecoinvent", biosphere_database_name=bio, use_mp=True
        )
        lap("extract")
        soup.apply_strategies()
        lap("strategies")
        out["datasets"], out["exchanges"], out["unlinked"], *_ = soup.statistics(print_stats=False)
        if expect is not None and {k: out[k] for k in expect} != expect:
            msg = f"synthetic import gave {[out[k] for k in expect]}, expected {list(expect.values())}"
            raise ValueError(msg)
        if size == "all" and not soup.all_linked:
            msg = f"full release has {out['unlinked']} unlinked exchanges"
            raise ValueError(msg)
        if not soup.all_linked:
            soup.drop_unlinked(i_am_reckless=True)
        if os.environ.get("PROFILE_WRITE"):
            import cProfile  # noqa: PLC0415
            import pstats  # noqa: PLC0415

            with cProfile.Profile() as prof:
                soup.write_database()
            pstats.Stats(prof, stream=sys.stderr).sort_stats("cumulative").print_stats(40)
        else:
            soup.write_database()
        lap("write")
    out["total"] = {"wall": round(sum(v["wall"] for v in out.values() if isinstance(v, dict)), 2), **usage()}
    out["total"]["cpu"] = round(out["total"]["cpu"], 2)
    return out


def driver(release: str, sizes: str, pythons: list[str]) -> int:
    """Run each size with each python in its own process; prints one JSON line per import."""
    rc = 0
    for py in pythons:  # page cache and .pyc files, so the first timed import is not the only cold one
        subprocess.run([py, "-I", "-W", "ignore", "-c", "import bw2io"], capture_output=True, check=False)  # noqa: S603 - pythons the caller names
    # Rounds outermost and pythons interleaved, so drift over the night hits every release alike.
    for rnd in range(1, ROUNDS + 1):
        for size in sizes.split(","):
            for py in pythons:
                t = time.perf_counter()
                p = subprocess.run(  # noqa: S603 - pythons the caller names, this script
                    [py, "-I", "-W", "ignore", __file__, "--one", release, size],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                line = p.stdout.strip().splitlines()[-1:] if p.returncode == 0 else []
                if not line:
                    rc = 1
                    # The last three lines only: a bw2io error message can quote a dataset.
                    tail = p.stderr.strip().splitlines()[-3:]
                    error = {"size": size, "python": py, "exit": p.returncode, "error": tail}
                    line = [json.dumps(error | {"wall": round(time.perf_counter() - t, 1)})]
                print(f"round {rnd} {line[0]}", flush=True)
    return rc


if __name__ == "__main__":
    if sys.argv[1] == "--one":
        print(json.dumps(one(sys.argv[2], sys.argv[3])))
    else:
        sys.exit(driver(sys.argv[1], sys.argv[2], sys.argv[3:] or [sys.executable]))
