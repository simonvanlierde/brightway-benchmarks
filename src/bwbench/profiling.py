"""Profile one benchmark case with pyinstrument: ``python -m bwbench.profiling SUBJECT CASE [NAME=VALUE...]``.

The case is a ``@bench`` function of ``benchmarks/bench_SUBJECT/``, set up through
``Bench.prepare`` and called through ``Prepared``, so the profile covers exactly the call asv
times. The setup, the check and the teardown are outside it. ``just profile`` runs this in the box.
The HTML report and the speedscope JSON go to ``.asv/profiles/``, named by ``profile_name``.
"""

from __future__ import annotations

import importlib
import os
import pkgutil
import sys
from importlib.metadata import version
from pathlib import Path

from bwbench.bench import Bench, benches

OUT = Path(".asv/profiles")


def profile_name(subject: str, case: str, params: dict[str, str], release: str, packages: list[str]) -> str:
    """The files' common name: subject, case, each parameter as ``name=value``, the release, then ``with=`` packages."""
    return "-".join(
        [subject, case, *(f"{k}={v}" for k, v in params.items()), release, *(f"with={p}" for p in packages)]
    )


def parse_params(args: list[str]) -> dict[str, str]:
    """``NAME=VALUE`` arguments as a dict; anything else, or a name given twice, stops the profile."""
    params: dict[str, str] = {}
    for a in args:
        name, eq, value = a.partition("=")
        if not eq or not name or name in params:
            msg = f"parameters are NAME=VALUE, each name once; got {a}"
            raise SystemExit(msg)
        params[name] = value
    return params


def typed(bench: Bench, params: dict[str, str]) -> dict[str, object]:
    """PARAMS with each value cast to the type of the case's declared values (``demands=3`` is an int).

    Values are not checked against the declared ones: those come from the knobs' smoke defaults, and a
    profile usually wants a full size such as ``ecoinvent``.
    """
    if set(params) != set(bench.params):
        msg = f"{bench.name} takes {', '.join(bench.params) or 'no parameters'}; got {', '.join(params) or 'none'}"
        raise SystemExit(msg)
    return {k: type(bench.params[k][0])(v) for k, v in params.items()}


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


def profile(bench: Bench, params: dict[str, object], name: str, out: Path = OUT) -> list[Path]:
    """Profile one timed call of ``bench`` at ``params``; write ``name`` + ``.html`` and ``.speedscope.json``."""
    from pyinstrument import Profiler  # noqa: PLC0415 - only the profile environment has it
    from pyinstrument.renderers import SpeedscopeRenderer  # noqa: PLC0415

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
    """Parse ``SUBJECT CASE [NAME=VALUE...]``, profile, and print the files.

    ``$BWBENCH_PROFILE_WITH`` names the packages installed on top (profile.sh's ``with=``), for the name.
    """
    if len(argv) < 2:
        msg = "usage: python -m bwbench.profiling SUBJECT CASE [NAME=VALUE...]"
        raise SystemExit(msg)
    subject, case, *extra = argv
    params = parse_params(extra)
    sys.path.insert(0, "benchmarks")
    bench = find_case(subject, case)
    packages = os.environ.get("BWBENCH_PROFILE_WITH", "").split()
    name = profile_name(subject, case, params, version(subject), packages)
    for path in profile(bench, typed(bench, params), name):
        sys.stdout.write(f"{path}\n")


if __name__ == "__main__":
    main(sys.argv[1:])
