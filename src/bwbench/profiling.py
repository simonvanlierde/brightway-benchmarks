"""Profile one benchmark case with pyinstrument: ``python -m bwbench.profiling SUBJECT CASE SIZE [NAME=VALUE...]``.

The case is a ``@bench`` function of ``benchmarks/bench_SUBJECT/``, set up through
``Bench.prepare`` and called through ``Prepared``, so the profile covers exactly the call asv
times. The setup, the check and the teardown are outside it. ``just profile`` runs this in the box.
The HTML report and the speedscope JSON go to ``.asv/profiles/``, named by ``profile_name``.
"""

from __future__ import annotations

import importlib
import pkgutil
import sys
from importlib.metadata import version
from pathlib import Path

from bwbench.bench import Bench, benches

OUT = Path(".asv/profiles")


def profile_name(subject: str, case: str, params: dict[str, str], release: str) -> str:
    """The files' common name: subject, case, each parameter as ``name=value`` in order, and the release."""
    return "-".join([subject, case, *(f"{k}={v}" for k, v in params.items()), release])


def find_case(subject: str, case: str) -> Bench:
    """The one ``@bench`` function named ``case`` in the modules of ``benchmarks/bench_<subject>``."""
    package = importlib.import_module(f"bench_{subject}")
    found = [
        b
        for m in pkgutil.iter_modules(package.__path__)
        if m.name.startswith("bench_")
        for b in benches(vars(importlib.import_module(f"{package.__name__}.{m.name}")))
        if b.name == case
    ]
    if len(found) != 1:
        msg = f"{subject}: {len(found)} benchmarks named {case}"
        raise SystemExit(msg)
    return found[0]


def profile(bench: Bench, params: dict[str, str], name: str, out: Path = OUT) -> list[Path]:
    """Profile one timed call of ``bench`` at ``params``; write ``name`` + ``.html`` and ``.speedscope.json``."""
    from pyinstrument import Profiler  # noqa: PLC0415 - only the profile environment has it
    from pyinstrument.renderers import SpeedscopeRenderer  # noqa: PLC0415

    if set(params) != set(bench.params):
        msg = f"{bench.name} takes {', '.join(bench.params) or 'no parameters'}; got {', '.join(params) or 'none'}"
        raise SystemExit(msg)
    prepared = bench.prepare(**params)
    profiler = Profiler()
    try:
        profiler.start()
        try:
            result = prepared()
        finally:
            profiler.stop()
        prepared.verify(result)  # a profile of a wrong answer explains nothing
    finally:
        prepared.teardown()
    out.mkdir(parents=True, exist_ok=True)
    files = [out / f"{name}.html", out / f"{name}.speedscope.json"]
    files[0].write_text(profiler.output_html())
    files[1].write_text(profiler.output(SpeedscopeRenderer()))
    return files


def main(argv: list[str]) -> None:
    """Parse ``SUBJECT CASE SIZE [NAME=VALUE...]``, profile, and print the files."""
    if len(argv) < 3:
        msg = "usage: python -m bwbench.profiling SUBJECT CASE SIZE [NAME=VALUE...]"
        raise SystemExit(msg)
    subject, case, size, *extra = argv
    params = {"size": size} | dict(e.split("=", 1) for e in extra)
    sys.path.insert(0, "benchmarks")
    name = profile_name(subject, case, params, version(subject))
    for path in profile(find_case(subject, case), params, name):
        sys.stdout.write(f"{path}\n")


if __name__ == "__main__":
    main(sys.argv[1:])
