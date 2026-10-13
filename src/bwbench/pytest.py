"""pytest-codspeed adapter: ``tests(globals())`` at the end of a benchmark module adds one test per ``@bench``."""

from __future__ import annotations

import inspect
from typing import Any

import pytest

from bwbench.bench import Bench, benches


def tests(namespace: dict[str, Any]) -> None:
    """Add a ``test_<name>`` for each benchmark in ``namespace``, parametrized and marked."""
    for b in benches(namespace):
        namespace[f"test_{b.name}"] = _test(b)


def _test(b: Bench) -> Any:
    def test(benchmark: Any, **params: Any) -> None:
        state: dict[str, Any] = {}

        def setup() -> tuple[tuple, dict]:
            state["run"] = b.prepare(**params)
            return (), {}

        def target() -> None:
            state["result"] = state["run"]()

        try:
            benchmark.pedantic(target, setup=setup, rounds=1, iterations=1)
        except NotImplementedError as e:
            pytest.skip(str(e))
        try:
            state["run"].verify(state["result"])
        finally:
            state["run"].teardown()
        # shortcut: track values are asv history only and are not recorded here; add them as
        # benchmark extra info if a PR gate ever needs one.

    test.__name__ = f"test_{b.name}"
    # pytest reads fixture and parameter names from the signature, not from **params.
    kind = inspect.Parameter.KEYWORD_ONLY
    test.__signature__ = inspect.Signature(  # ty: ignore[unresolved-attribute]
        [inspect.Parameter(n, kind) for n in ["benchmark", *b.params]]
    )
    for name, values in reversed(b.params.items()):
        test = pytest.mark.parametrize(name, values)(test)
    return pytest.mark.benchmark(test)
