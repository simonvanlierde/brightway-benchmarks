"""asv adapter: ``classes(__name__)`` at the end of a benchmark module adds one asv class per ``@bench``.

Benchmarks with the same ``asv`` name become methods of one class; its setup prepares all of
them before each method, so give them the same ``params``.
"""

from __future__ import annotations

import functools
import hashlib
import json
import os
import sys
import time
from importlib import metadata
from pathlib import Path
from typing import TYPE_CHECKING, Any

from bwbench import first_time
from bwbench.bench import Bench, Prepared, benches
from bwbench.synth import GENERATOR_VERSION, data_root, profile_version

if TYPE_CHECKING:
    from collections.abc import Callable


def classes(module: str) -> list[type]:
    """Build the asv classes for the benchmarks in ``module`` and set them on it."""
    mod = sys.modules[module]
    groups: dict[str, list[Bench]] = {}
    for b in benches(vars(mod)):
        groups.setdefault(b.asv or b.name.title().replace("_", ""), []).append(b)
    made = [_asv_class(name, group) for name, group in groups.items()]
    for cls in made:
        cls.__module__ = module
        setattr(mod, cls.__name__, cls)
    return made


def _asv_class(name: str, group: list[Bench]) -> type:
    params = group[0].params
    if any(b.params != params for b in group):
        msg = f"benchmarks in asv class {name} need the same params"
        raise ValueError(msg)
    names = list(params)
    by_name = {b.name: b for b in group}

    def setup(self: Any, *args: Any) -> None:
        self.prepared = {}
        self.results = {}
        for b in group:
            self.prepared[b.name] = b.prepare(**dict(zip(names, args, strict=True)))
        self.usage = _usage()  # last, so the setup's own work is not counted

    def teardown(self: Any, *args: Any) -> None:
        # The check runs here, outside the timed call; asv reports a raise as a failed benchmark.
        prepared: dict[str, Prepared] = getattr(self, "prepared", {})
        _log_usage(self, args)
        try:
            _verify_once(type(self), by_name, prepared, getattr(self, "results", {}), args)
        finally:
            for p in prepared.values():
                p.teardown()

    body: dict[str, Any] = {
        "params": [params[n] for n in names],
        "param_names": names,
        "setup": setup,
        "teardown": teardown,
        "number": 1,  # one run per setup
        "warmup_time": 0,  # asv's warm-up calls the benchmark again without a new setup
        # asv's own version hashes this adapter, not the benchmark, so the profiles set it.
        "version": profile_version() if "size" in params else GENERATOR_VERSION,
        "timeout": 900,
        # asv's default is 2, each round in a new process. One halves a run whose samples
        # each take tens of seconds (SuperLU at ecoinvent size) and adds noise to short ones.
        "rounds": int(os.environ.get("BWBENCH_ROUNDS", "2")),
    }
    methods: dict[str, Any] = {}
    for b in group:
        body.update(b.options)
        new: dict[str, Any] = {f"time_{b.name}": _time(b.name)}
        if b.peakmem:
            new[f"peakmem_{b.name}"] = _peak(b.name)
        new |= {f"track_{t}": _track(b.name, fn, f"track_{t}") for t, fn in b.track.items()}
        if b.error:
            new[f"track_{b.error}"] = _error(b.name, f"track_{b.error}")
        if clash := methods.keys() & new.keys():
            msg = f"asv class {name}: two benchmarks define {sorted(clash)}"
            raise ValueError(msg)
        methods |= new
    return type(name, (), body | methods)


def _usage() -> tuple[float, float, int]:
    """(wall seconds, CPU seconds of this process's threads, involuntary context switches so far)."""
    import resource  # noqa: PLC0415 - Unix only, and only the round log needs it

    ru = resource.getrusage(resource.RUSAGE_SELF)
    return time.perf_counter(), ru.ru_utime + ru.ru_stime, ru.ru_nivcsw


def _log_usage(obj: Any, args: tuple) -> None:
    """Append one JSON line per timed sample: its wall and CPU time and involuntary context switches.

    Only when ``BWBENCH_ROUNDLOG`` names the log file. Only time_ calls fill ``results``, so only
    time_ samples are logged. The span runs from the end of setup to teardown, so it includes
    asv's timer. ``scripts/noise_summary.py`` reads the log.
    """
    log = os.environ.get("BWBENCH_ROUNDLOG")
    results = getattr(obj, "results", {})
    if not log or not results:
        return
    log = Path(log)
    cls = type(obj)
    wall, cpu, nivcsw = (b - a for a, b in zip(obj.usage, _usage(), strict=True))
    log.parent.mkdir(parents=True, exist_ok=True)
    env = os.environ.get("ASV_ENV_NAME") or Path(sys.prefix).name
    with log.open("a") as f:
        for bench_name in results:
            entry = {
                "case": f"{cls.__module__.rsplit('.', 1)[-1]}.{cls.__name__}.time_{bench_name}",  # as asv names it
                "params": ", ".join(map(repr, args)),
                "env": env,
                "wall": wall,
                "cpu": cpu,
                "nivcsw": nivcsw,
            }
            f.write(json.dumps(entry) + "\n")


def _verify_once(
    cls: type, benches: dict[str, Bench], prepared: dict[str, Prepared], results: dict[str, Any], args: tuple
) -> None:
    """Check each timed result once per parameter set: later samples run the same code on the same data.

    The check's error and the ``track`` values of that result are recorded, so the ``track_``
    methods asv runs later read them instead of running the case again.
    """
    for bench_name, result in results.items():
        if first_time("verify", cls.__name__, bench_name, *args):
            b = benches[bench_name]
            error = prepared[bench_name].verify(result)
            values = {f"track_{b.error}": error} if b.error else {}
            try:
                values |= {f"track_{t}": fn(result) for t, fn in b.track.items()}
            except Exception:  # noqa: BLE001 - the track_ method reruns the case and reports it
                values = {f"track_{b.error}": error} if b.error else {}
            _record(cls, bench_name, args, values)


@functools.cache
def _record_file() -> Path | None:
    """This environment's record of check results, or None outside a box run (no ``BWBENCH_COMMIT``).

    Keyed by the benchmark code's commit and source (a run on uncommitted edits shares the
    commit), the environment and every installed distribution's version, so a record never
    crosses releases or code changes. ``_case`` adds the benchmark module's own source.
    """
    commit = os.environ.get("BWBENCH_COMMIT")
    if not commit:
        return None
    dists = sorted(f"{d.metadata['Name']}=={d.version}" for d in metadata.distributions())
    source = [p.read_text() for p in sorted(Path(__file__).parent.glob("*.py"))]
    key = hashlib.sha256("\n".join([commit, sys.prefix, *dists, *source]).encode()).hexdigest()[:16]
    # shortcut: one small file per environment and code commit, never pruned; prune with the cache.
    return data_root() / "tracks" / f"{key}.jsonl"


def _case(cls: type, bench_name: str, args: tuple) -> str:
    return f"{cls.__module__}.{cls.__name__}.{bench_name}{args!r}@{_module_hash(cls.__module__)}"


@functools.cache
def _module_hash(module: str) -> str:
    path = getattr(sys.modules.get(module), "__file__", None)
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:16] if path else ""


def _record(cls: type, bench_name: str, args: tuple, values: dict[str, Any]) -> None:
    path = _record_file()
    if path is None or not values:
        return
    try:
        line = json.dumps({"case": _case(cls, bench_name, args), **values})
    except (TypeError, ValueError):
        return  # a value JSON cannot hold: the track_ method computes it itself
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(line + "\n")


def _recorded(cls: type, bench_name: str, args: tuple, method: str) -> tuple[bool, Any]:
    """(True, value) when the timed run of this case recorded ``method``'s value, else (False, None)."""
    path = _record_file()
    if path is None or not path.exists():
        return False, None
    case = _case(cls, bench_name, args)
    for line in reversed(path.read_text().splitlines()):
        entry = json.loads(line)
        if entry["case"] == case and method in entry:
            return True, entry[method]
    return False, None


def _time(bench_name: str) -> Callable[..., None]:
    def time(self: Any, *args: Any) -> None:
        self.results[bench_name] = self.prepared[bench_name]()

    return time


def _peak(bench_name: str) -> Callable[..., None]:
    """A ``peakmem_`` method: asv reads the process's peak resident memory, so nothing is kept."""

    def peak(self: Any, *args: Any) -> None:
        self.prepared[bench_name]()

    return peak


def _track(bench_name: str, fn: Callable[[Any], float], method: str) -> Callable[..., float]:
    def track(self: Any, *args: Any) -> float:
        found, value = _recorded(type(self), bench_name, args, method)
        return value if found else fn(self.prepared[bench_name]())

    return track


def _error(bench_name: str, method: str) -> Callable[..., float | None]:
    """A ``track_`` method recording the check's relative error."""

    def error(self: Any, *args: Any) -> float | None:
        found, value = _recorded(type(self), bench_name, args, method)
        if found:
            return value
        prepared = self.prepared[bench_name]
        return prepared.verify(prepared())

    return error
