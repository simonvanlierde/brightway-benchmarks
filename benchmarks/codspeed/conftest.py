"""Show warnings from the Brightway code under test instead of failing on them.

The unit tests turn every warning into an error (`filterwarnings` in pyproject.toml). These
suites time released Brightway code, whose own warnings, such as bw2calc's note that
pypardiso is missing, are not ours to fail on.
"""

import pytest


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("filterwarnings", "default")
