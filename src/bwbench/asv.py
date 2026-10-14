"""asv adapter: ``classes(__name__)`` at the end of a benchmark module adds one asv class per ``@bench``.

Benchmarks with the same ``asv`` name become methods of one class; its setup prepares all of
them before each method, so give them the same ``params``.
"""

from __future__ import annotations

import os
import sys
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

    def setup(self: Any, *args: Any) -> None:
        self.prepared = {}
        self.results = {}
        for b in group:
            self.prepared[b.name] = b.prepare(**dict(zip(names, args, strict=True)))

    def teardown(self: Any, *args: Any) -> None:
        # The check runs here, outside the timed call; asv reports a raise as a failed benchmark.
        prepared: dict[str, Prepared] = getattr(self, "prepared", {})
        try:
            _verify_once(name, prepared, getattr(self, "results", {}), args)
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
        new |= {f"track_{t}": _track(b.name, fn) for t, fn in b.track.items()}
        if b.error:
            new[f"track_{b.error}"] = _error(b.name)
        if clash := methods.keys() & new.keys():
            msg = f"asv class {name}: two benchmarks define {sorted(clash)}"
            raise ValueError(msg)
        methods |= new
    return type(name, (), body | methods)


def _verify_once(cls_name: str, prepared: dict[str, Prepared], results: dict[str, Any], args: tuple) -> None:
    """Check each timed result once per parameter set: later samples run the same code on the same data."""
    for bench_name, result in results.items():
        if first_time("verify", cls_name, bench_name, *args):
            prepared[bench_name].verify(result)


def _time(bench_name: str) -> Callable[..., None]:
    def time(self: Any, *args: Any) -> None:
        self.results[bench_name] = self.prepared[bench_name]()

    return time


def _track(bench_name: str, fn: Callable[[Any], float]) -> Callable[..., float]:
    def track(self: Any, *args: Any) -> float:
        return fn(self.prepared[bench_name]())

    return track


def _error(bench_name: str) -> Callable[..., float | None]:
    """A ``track_`` method recording the check's relative error."""

    def error(self: Any, *args: Any) -> float | None:
        prepared = self.prepared[bench_name]
        return prepared.verify(prepared())

    return error
