"""Atheris harness for the validator of contributed result files: ``bwbench validate --contribution``.

The input is untrusted: contributors send these files by pull request, and the ``contributed``
workflow validates them. The contract is an exit code of 0 or 1 with the problems on stderr;
any other exception, or a hang, is a bug. Half the inputs are raw bytes, the rest a valid file
with some of its values swapped for boundary values or fuzzed ones. It is not a pytest test (the
name does not match ``test_*.py``); ``test_ratios_fuzz.py`` holds the same contract for pytest.

Run: ``PYTHONPATH=src uv run --no-project --python 3.13 --with atheris==3.1.0 --with jsonschema==4.26.0
--with rfc3339-validator==0.1.4 python tests/fuzz_ratios.py -max_total_time=60``
"""

import importlib.util
import json
import sys
import tempfile
from pathlib import Path

import atheris  # ty: ignore[import-not-found]  # installed by the run command, not a project dependency

spec = importlib.util.spec_from_file_location("ratios_corpus", Path(__file__).with_name("ratios_corpus.py"))
assert spec is not None
assert spec.loader is not None
ratios_corpus = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ratios_corpus)

BASE = ratios_corpus.valid_doc()
FOLDER = Path(tempfile.mkdtemp(prefix="fuzz-ratios-"))
EDITS = 4


def value(fdp: atheris.FuzzedDataProvider) -> object:
    """One replacement value: a boundary value, or one the fuzzer builds."""
    match fdp.ConsumeIntInRange(0, 4):
        case 0:
            return ratios_corpus.SPECIALS[fdp.ConsumeIntInRange(0, len(ratios_corpus.SPECIALS) - 1)]
        case 1:
            return fdp.ConsumeInt(8)
        case 2:
            return fdp.ConsumeFloat()
        case 3:
            return fdp.ConsumeUnicodeNoSurrogates(fdp.ConsumeIntInRange(0, 40))
        case _:
            return [fdp.ConsumeFloat() for _ in range(fdp.ConsumeIntInRange(0, 5))]


def one_input(data: bytes) -> None:
    """Feed the validator one fuzzed file; it may refuse it, not crash."""
    fdp = atheris.FuzzedDataProvider(data)
    if fdp.ConsumeBool():
        raw = fdp.ConsumeBytes(len(data))
    else:
        doc = BASE
        for _ in range(fdp.ConsumeIntInRange(1, EDITS)):
            doc = ratios_corpus.edit(doc, fdp.ConsumeIntInRange(0, 10_000), value(fdp), drop=fdp.ConsumeBool())
        raw = json.dumps(doc).encode()
    ratios_corpus.check(raw, FOLDER)


if __name__ == "__main__":
    atheris.instrument_all()  # the validator was imported already, so import hooks would not see it
    atheris.Setup(sys.argv, one_input)
    atheris.Fuzz()
