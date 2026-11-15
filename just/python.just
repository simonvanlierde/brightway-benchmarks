# Install the venv, writing uv.lock if it is missing or stale. CI uses --locked.
py-sync:
    uv sync

# What CI runs: lint, format check, types, tests with the coverage gate, dependency audit.
py-check:
    uv run ruff check
    uv run ruff format --check
    uv run ty check
    uv run pytest --cov
    uv audit --locked --preview-features audit-command

# Fix what ruff can fix, then format.
py-fmt:
    uv run ruff check --fix
    uv run ruff format

# Tests with a coverage summary.
py-cov:
    uv run pytest --cov --cov-report=term-missing

# Tests only; extra arguments reach pytest (`just py-test -k name`).
py-test *args:
    uv run pytest {{ args }}

# The tests on every Python version python.yml tests, each in a throwaway environment.
py-matrix:
    for v in 3.13 3.14 3.15; do uv run --isolated --locked --python "$v" pytest || exit 1; done
