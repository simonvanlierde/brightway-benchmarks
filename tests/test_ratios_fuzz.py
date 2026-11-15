"""``bwbench validate --contribution`` on hostile files: it refuses them, it does not crash.

The same contract as ``fuzz_ratios.py``, without Atheris, so ``pytest`` covers it.
"""

import importlib.util
import json
from pathlib import Path

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from bwbench.ratios import contribution_problems, problems

spec = importlib.util.spec_from_file_location("ratios_corpus", Path(__file__).with_name("ratios_corpus.py"))
assert spec is not None
assert spec.loader is not None
corpus = importlib.util.module_from_spec(spec)
spec.loader.exec_module(corpus)
SPECIALS, check, edit, valid_doc = corpus.SPECIALS, corpus.check, corpus.edit, corpus.valid_doc

BASE = valid_doc()
values = st.one_of(
    st.sampled_from(SPECIALS),
    st.integers(),
    st.floats(),
    st.text(max_size=40),
    st.lists(st.floats(), max_size=5),
)
folder = settings(suppress_health_check=[HealthCheck.function_scoped_fixture], deadline=2000)


def test_the_base_file_is_valid(tmp_path: Path):
    check(json.dumps(BASE).encode(), tmp_path)
    assert problems(BASE) == []
    assert contribution_problems(tmp_path / "ratios/contributed/test-machine/2026-11-14.json", BASE) == []


@folder
@given(st.lists(st.tuples(st.integers(0, 10_000), values, st.booleans()), min_size=1, max_size=4))
def test_an_edited_file_is_refused_or_accepted(tmp_path: Path, edits: list[tuple[int, object, bool]]):
    doc = BASE
    for index, value, drop in edits:
        doc = edit(doc, index, value, drop=drop)
    check(json.dumps(doc).encode(), tmp_path)


@folder
@given(st.binary(max_size=2000))
def test_any_bytes_are_refused_or_accepted(tmp_path: Path, raw: bytes):
    check(raw, tmp_path)
