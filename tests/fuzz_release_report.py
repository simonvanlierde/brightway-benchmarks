"""Atheris harness for ``scripts/release_report.py``'s ``tally``.

The input is not untrusted: asv writes these result files on our own machine. The harness
exists for the OpenSSF Scorecard Fuzzing check, which looks for ``import atheris``. It is not
a pytest test (the name does not match ``test_*.py``).

Run: ``uv run --no-project --python 3.12 --with atheris==3.1.0 python tests/fuzz_release_report.py
-max_total_time=60``
"""

import contextlib
import importlib.util
import sys
from pathlib import Path

import atheris  # ty: ignore[unresolved-import]  # installed by the run command, not a project dependency

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "release_report.py"
spec = importlib.util.spec_from_file_location("release_report", SCRIPT)
assert spec is not None
assert spec.loader is not None
release_report = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release_report)

# The exceptions ``tally`` documents for text that is not JSON or not asv's shape.
MALFORMED = (ValueError, AttributeError, IndexError, KeyError, TypeError)


def one_input(data: bytes) -> None:
    """Feed ``tally`` one fuzzed string; only its documented errors are fine."""
    text = atheris.FuzzedDataProvider(data).ConsumeUnicodeNoSurrogates(len(data))
    with contextlib.suppress(*MALFORMED):
        release_report.tally(text)


if __name__ == "__main__":
    atheris.instrument_all()  # the script is loaded by path, so import hooks would not see it
    atheris.Setup(sys.argv, one_input)
    atheris.Fuzz()
