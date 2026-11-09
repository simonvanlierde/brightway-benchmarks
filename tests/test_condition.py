"""System.condition_estimate: the 1-norm condition number the real-size runs log next to their times."""

import numpy as np

from bwbench.synth import system


def test_condition_estimate_matches_the_exact_value_and_leaves_the_global_rng_alone():
    s = system("smoke")
    exact = np.linalg.cond(s.technosphere().toarray(), 1)
    np.random.seed(7)  # noqa: NPY002 - scipy's onenormest draws from the global generator
    before = np.random.get_state()  # noqa: NPY002
    first = s.condition_estimate()
    after = np.random.get_state()  # noqa: NPY002
    assert np.array_equal(after[1], before[1])
    assert first == s.condition_estimate()  # deterministic
    assert 0.3 * exact <= first <= exact * (1 + 1e-9)  # onenormest is a lower bound, usually exact
