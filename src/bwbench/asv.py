"""asv adapter: ``classes(__name__)`` at the end of a benchmark module adds one asv class per ``@bench``.

Benchmarks with the same ``asv`` name become methods of one class, so give them the same
``params``. asv runs every setup it finds for a method (module, class, then the method's own),
so the class has none: each method carries its own setup, which prepares just its bench. A
``track_`` method's setup prepares its case only when the timed run left no value to read, and
raises a skipped case's NotImplementedError there, where asv reads it as a skip.
asv-runner 0.2.5 ``benchmarks/_base.py`` (``Benchmark.__init__``, ``do_setup``) looks the
method's ``setup`` up on the bound method, which reaches the function's attribute and calls it
with the params only. It has no ``self``, so the state lives in one object shared by the class.
"""

from __future__ import annotations

import functools
import hashlib
import json
import os
import sys
import threading
import time
from importlib import metadata
from pathlib import Path
from typing import TYPE_CHECKING, Any

from bwbench import first_time
from bwbench.bench import Bench, Prepared, benches
from bwbench.synth import GENERATOR_VERSION, profile_version

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

    state = _State()

    def prepare(name: str, args: tuple) -> None:
        old = state.prepared.pop(name, None)
        if old is not None:
            old.teardown()
        state.prepared[name] = by_name[name].prepare(**dict(zip(names, args, strict=True)))

    def teardown(self: Any, *args: Any) -> None:
        # The check runs here, outside the timed call; asv reports a raise as a failed benchmark.
        prepared, results = state.prepared, state.results
        _log_usage(state, type(self), args)
        try:
            _verify_once(type(self), by_name, prepared, results, args)
        finally:
            for p in prepared.values():
                p.teardown()
            state.reset()

    body: dict[str, Any] = {
        "params": [params[n] for n in names],
        "param_names": names,
        "state": state,
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
        new = _methods(state, prepare, b)
        if clash := methods.keys() & new.keys():
            msg = f"asv class {name}: two benchmarks define {sorted(clash)}"
            raise ValueError(msg)
        methods |= new
    state.cls = type(name, (), body | methods)
    return state.cls


def _methods(state: _State, prepare: Callable[[str, tuple], None], b: Bench) -> dict[str, Any]:
    """The asv methods of one bench; each has a setup, the ``track_`` ones prepare only without a record."""
    timed: dict[str, Any] = {f"time_{b.name}": _time(state, b.name)}
    if b.peakmem:
        timed[f"peakmem_{b.name}"] = _peak(state, b.name)
    for method in timed.values():
        method.setup = _setup(state, prepare, b.name)
    tracked: dict[str, Any] = {f"track_{t}": _track(state, b.name, fn, f"track_{t}") for t, fn in b.track.items()}
    if b.error:
        tracked[f"track_{b.error}"] = _error(state, b.name, f"track_{b.error}")
    for method, fn in tracked.items():
        fn.setup = _track_setup(state, prepare, b.name, method)
    return timed | tracked


class _State:
    """What one process's setups leave for its method and teardown."""

    cls: type  # the asv class, set once it exists

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.prepared: dict[str, Prepared] = {}
        self.results: dict[str, Any] = {}
        self.usage: tuple[float, float, int] | None = None
        self.energy: _Meter | None = None


def _setup(state: _State, prepare: Callable[[str, tuple], None], bench_name: str) -> Callable[..., None]:
    def setup(*args: Any) -> None:
        state.results = {}
        prepare(bench_name, args)
        state.usage, state.energy = _usage(), _energy()  # last, so the setup's own work is not counted

    return setup


def _track_setup(
    state: _State, prepare: Callable[[str, tuple], None], bench_name: str, method: str
) -> Callable[..., None]:
    """Prepare the case only when the timed run left no value to read.

    A skipped case raises NotImplementedError here, the only place asv reads it as a skip.
    """

    def setup(*args: Any) -> None:
        if not _recorded(state.cls, bench_name, args, method)[0]:
            prepare(bench_name, args)

    return setup


def _usage() -> tuple[float, float, int]:
    """(wall seconds, CPU seconds of this process's threads, involuntary context switches so far)."""
    import resource  # noqa: PLC0415 - Unix only, and only the round log needs it

    ru = resource.getrusage(resource.RUSAGE_SELF)
    return time.perf_counter(), ru.ru_utime + ru.ru_stime, ru.ru_nivcsw


_energy_warned = False


def _rapl() -> Path:
    # scripts/box.sh mounts the counter at /run/rapl: Docker hides /sys/devices/virtual/powercap.
    return Path(os.environ.get("BWBENCH_RAPL", "/sys/class/powercap/intel-rapl:0"))


# Seconds between counter readings, and the longest gap trusted not to hide a whole counter cycle.
# The counter restarts at 0 past max_energy_range_uj (262 kJ on an i9-14900KF); 60 s matches
# scripts/idle_energy.py.
_ENERGY_INTERVAL = 5.0
_ENERGY_MAX_GAP = 60.0


class _Meter:
    """Sums the CPU package's energy counter (Intel RAPL) in short deltas from a background thread.

    Two readings alone cannot tell how many times the counter wrapped between them, and asv lets a
    sample run for 1800 s. A gap between readings above ``_ENERGY_MAX_GAP``, or a failed read, voids
    the sample's energy rather than undercounting it.
    """

    def __init__(self, rapl: Path) -> None:
        self.counter = rapl / "energy_uj"
        self.span = int((rapl / "max_energy_range_uj").read_text())
        self.value, self.at = int(self.counter.read_text()), time.monotonic()
        self.joules: float | None = 0.0
        self.done = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _read(self) -> None:
        try:
            value, at = int(self.counter.read_text()), time.monotonic()
        except (OSError, ValueError):
            self.joules = None
            return
        if at - self.at > _ENERGY_MAX_GAP:
            self.joules = None
        if self.joules is not None:
            self.joules += (value - self.value) % self.span / 1e6
        self.value, self.at = value, at

    def _run(self) -> None:
        while not self.done.wait(_ENERGY_INTERVAL):
            self._read()

    def stop(self) -> float | None:
        """Joules since the meter started, or None when they cannot be trusted."""
        self.done.set()
        self.thread.join()
        self._read()
        return self.joules


def _energy() -> _Meter | None:
    """A running energy meter when ``BWBENCH_ENERGY=1`` and the counter can be read."""
    global _energy_warned  # noqa: PLW0603 - warn once per process, not once per sample
    if os.environ.get("BWBENCH_ENERGY") != "1":
        return None
    try:
        return _Meter(_rapl())
    except (OSError, ValueError) as e:
        if not _energy_warned:
            sys.stderr.write(f"bwbench: BWBENCH_ENERGY=1 but no energy is logged: {e}\n")
            _energy_warned = True
        return None


def _log_usage(state: _State, cls: type, args: tuple) -> None:
    """Append one JSON line per timed sample: its wall and CPU time and involuntary context switches.

    Only when ``BWBENCH_ROUNDLOG`` names the log file. Only time_ calls fill ``results``, so only
    time_ samples are logged. The span runs from the end of setup to teardown, so it includes
    asv's timer. With ``BWBENCH_ENERGY=1`` the line also holds ``energy_j``, the whole CPU
    package's energy over that span. ``scripts/noise_summary.py`` and ``scripts/energy_summary.py``
    read the log.
    """
    meter = state.energy
    joules = None if meter is None else meter.stop()  # always, so no meter thread outlives its sample
    log = os.environ.get("BWBENCH_ROUNDLOG")
    results = state.results
    if not log or not results or state.usage is None:
        return
    log = Path(log)
    usage = _usage()
    wall, cpu, nivcsw = (b - a for a, b in zip(state.usage, usage, strict=True))
    energy = {} if joules is None else {"energy_j": joules}
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
            } | energy
            f.write(json.dumps(entry) + "\n")


def _verify_once(
    cls: type, benches: dict[str, Bench], prepared: dict[str, Prepared], results: dict[str, Any], args: tuple
) -> None:
    """Check each timed result once per parameter set: later samples run the same code on the same data.

    The check's error and the ``track`` values of that result are recorded, so the ``track_``
    methods asv runs later read them instead of running the case again. An empty record goes
    first, so a check that raises leaves no older value for them to read.
    """
    for bench_name, result in results.items():
        if first_time("verify", cls.__name__, bench_name, *args):
            b = benches[bench_name]
            _record(cls, bench_name, args, {})
            error = prepared[bench_name].verify(result)
            values = {f"track_{b.error}": error} if b.error else {}
            try:
                values |= {f"track_{t}": fn(result) for t, fn in b.track.items()}
            except Exception:  # noqa: BLE001 - the track_ method reruns the case and reports it
                values = {f"track_{b.error}": error} if b.error else {}
            _record(cls, bench_name, args, values)


@functools.cache
def _record_file() -> Path | None:
    """This environment's record of check results for this run, or None outside a box run.

    It lives in ``$HOME``, which ``scripts/in-box.sh`` makes new for every run, so a record
    never outlives its run. Inside one run, environments install one release after another
    into the same folder, so the key also holds every installed distribution's version and
    asv's commit. Outside the box (no ``BWBENCH_COMMIT``) nothing is recorded.
    """
    if not os.environ.get("BWBENCH_COMMIT"):
        return None
    dists = sorted(f"{d.metadata['Name']}=={d.version}" for d in metadata.distributions())
    parts = [sys.prefix, os.environ.get("ASV_COMMIT", ""), *dists]
    key = hashlib.sha256("\n".join(parts).encode()).hexdigest()[:16]
    return Path.home() / ".bwbench-tracks" / f"{key}.jsonl"


def _case(cls: type, bench_name: str, args: tuple) -> str:
    return f"{cls.__module__}.{cls.__name__}.{bench_name}{args!r}"


def _plain(value: Any) -> Any:
    """Numpy scalars as Python numbers, for ``json.dumps``."""
    if hasattr(value, "item"):
        return value.item()
    msg = f"{type(value).__name__} is not JSON"
    raise TypeError(msg)


def _record(cls: type, bench_name: str, args: tuple, values: dict[str, Any]) -> None:
    path = _record_file()
    if path is None:
        return
    try:
        line = json.dumps({"case": _case(cls, bench_name, args), **values}, default=_plain)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a") as f:
            f.write(line + "\n")
    except (TypeError, ValueError, OSError):
        return  # the track_ method computes the value itself


def _recorded(cls: type, bench_name: str, args: tuple, method: str) -> tuple[bool, Any]:
    """(True, value) when this case's newest record holds ``method``'s value, else (False, None)."""
    path = _record_file()
    if path is None or not path.exists():
        return False, None
    case = _case(cls, bench_name, args)
    for line in reversed(path.read_text().splitlines()):
        try:
            entry = json.loads(line)
        except ValueError:
            continue  # a line cut short by a killed process
        if entry.get("case") == case:
            return (True, entry[method]) if method in entry else (False, None)
    return False, None


def _time(state: _State, bench_name: str) -> Callable[..., None]:
    def time(self: Any, *args: Any) -> None:
        state.results[bench_name] = state.prepared[bench_name]()

    return time


def _peak(state: _State, bench_name: str) -> Callable[..., None]:
    """A ``peakmem_`` method: asv reads the process's peak resident memory, so nothing is kept."""

    def peak(self: Any, *args: Any) -> None:
        state.prepared[bench_name]()

    return peak


def _track(state: _State, bench_name: str, fn: Callable[[Any], float], method: str) -> Callable[..., float]:
    def track(self: Any, *args: Any) -> float:
        found, value = _recorded(type(self), bench_name, args, method)
        return value if found else fn(state.prepared[bench_name]())

    return track


def _error(state: _State, bench_name: str, method: str) -> Callable[..., float | None]:
    """A ``track_`` method recording the check's relative error."""

    def error(self: Any, *args: Any) -> float | None:
        found, value = _recorded(type(self), bench_name, args, method)
        if found:
            return value
        prepared = state.prepared[bench_name]
        return prepared.verify(prepared())

    return error
