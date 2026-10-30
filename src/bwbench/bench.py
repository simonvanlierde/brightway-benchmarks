"""The benchmark-to-runner seam: write a benchmark once, run it under asv or pytest-codspeed.

A benchmark is a setup function decorated with ``@bench`` that returns ``(run, expect)``.
``run`` is the timed call. ``expect`` checks its result, outside the timing, and is one of:

- a value the result must match within ``rtol``;
- a function of the result that raises on a wrong one and returns its relative error;
- ``UNCHECKED``.

The setup is never timed. It runs fresh before every timed call, which calls ``run`` once.
A setup that needs a teardown yields ``(run, expect)`` instead; the code after the
``yield`` runs once the result is checked.

The adapters in ``bwbench.asv`` and ``bwbench.pytest`` turn a module's benchmarks into asv
classes or pytest tests.
"""

from __future__ import annotations

import inspect
import sys
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from bwbench import check

if TYPE_CHECKING:
    from collections.abc import Callable, Generator


class NotApplicable(NotImplementedError):  # noqa: N818
    """The case does not apply to this environment's solver; a skip even where BWBENCH_STRICT is set."""


UNCHECKED = object()  # an ``expect`` that says on purpose that the result is not checked
# What a setup returns: ``(run, expect)``. Not named `Setup`: asv finds `setup` in a
# benchmark module ignoring case, and would call it.
type BenchSetup = tuple[Callable[[], Any], Any]


@dataclass
class Prepared:
    """One setup's ``run``, guarded to a single call, with the check and teardown that follow it."""

    bench: Bench
    _run: Callable[[], Any]
    expect: Any
    _rest: Generator | None = None
    calls: int = 0

    def __call__(self) -> Any:
        """The timed call; a second one raises."""
        self.calls += 1
        if self.calls > 1:
            msg = f"{self.bench.name}: run called twice after one setup"
            raise RuntimeError(msg)
        return self._run()

    def verify(self, result: Any) -> float | None:
        """Check ``result``; returns its relative error, or None when it is not checked."""
        if self.expect is UNCHECKED:
            return None
        if callable(self.expect):
            return self.expect(result)
        if self.bench.rtol is None:
            msg = f"{self.bench.name}: an expected value needs an rtol"
            raise ValueError(msg)
        return check(result, self.expect, self.bench.rtol, self.bench.name)

    def teardown(self) -> None:
        """Run the code after the setup's ``yield``, once."""
        rest, self._rest = self._rest, None
        if rest is not None:
            next(rest, None)


@dataclass(frozen=True)
class Bench:
    """One benchmark: its setup function and how the adapters present it."""

    setup: Callable[..., Any]
    params: dict[str, list[Any]]
    rtol: float | None
    track: dict[str, Callable[[Any], float]] = field(default_factory=dict)
    error: str | None = None  # record the check's relative error as asv ``track_<error>``
    asv: str | None = None  # asv class name; keeps a history's names when the function is renamed
    options: dict[str, Any] = field(default_factory=dict)  # more asv attributes, e.g. ``timeout``
    fresh_solver: bool = True
    peakmem: bool = False  # also record asv ``peakmem_<name>``

    @property
    def name(self) -> str:
        """The setup function's name: ``time_<name>`` in asv, ``test_<name>`` in pytest."""
        return getattr(self.setup, "__name__", "bench")

    def prepare(self, **params: Any) -> Prepared:
        """Run the setup and return its guarded ``run``."""
        rest = None
        if inspect.isgeneratorfunction(self.setup):
            rest = self.setup(**params)
            run, expect = next(rest)
        else:
            run, expect = self.setup(**params)
        if self.fresh_solver:
            free_pardiso()
        return Prepared(self, run, expect, rest)


def bench(
    params: dict[str, list[Any]] | None = None,
    *,
    rtol: float | None = None,
    track: dict[str, Callable[[Any], float]] | None = None,
    error: str | None = None,
    asv: str | None = None,
    fresh_solver: bool = True,
    peakmem: bool = False,
    **options: Any,
) -> Callable[[Callable[..., Any]], Bench]:
    """Mark a setup function as a benchmark.

    Args:
        params: parameter name to the values it takes; the adapters run every combination.
        rtol: relative tolerance of the check of ``run()`` against a plain ``expect`` value.
        track: name to a function of ``run()``'s result, recorded as an asv ``track_<name>``.
        error: record the check's relative error as asv ``track_<error>``.
        asv: the asv class name, so renaming the function does not break a history.
            Benchmarks that share one are methods of one class.
        fresh_solver: drop PyPardiso's factorization after the setup, so the timed call
            pays for its own. Turn it off where reusing the setup's factorization is the point.
        peakmem: also record asv's ``peakmem_<name>``, the process's peak resident memory. asv
            measures the setup too, so it covers building the inputs as well as the call.
        **options: further asv class attributes, such as ``timeout`` or ``repeat``.
    """
    return lambda fn: Bench(fn, params or {}, rtol, track or {}, error, asv, options, fresh_solver, peakmem)


def free_pardiso() -> None:
    """Drop the factorization PyPardiso's module-level solver keeps from its last solve.

    It skips factorizing a matrix it has just factorized, so without this the timed call
    after a checking setup would skip the work that SuperLU and UMFPACK pay for.
    """
    if "pypardiso" in sys.modules:
        from pypardiso.scipy_aliases import pypardiso_solver  # noqa: PLC0415

        pypardiso_solver.free_memory(everything=True)


def benches(namespace: dict[str, Any]) -> list[Bench]:
    """The benchmarks defined in a module namespace, in definition order."""
    return [v for v in namespace.values() if isinstance(v, Bench)]
