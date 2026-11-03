"""bwbench.profiling on a toy benchmark; no Brightway code runs here."""

import json
from pathlib import Path

import pytest

from bwbench import profiling
from bwbench.bench import UNCHECKED, bench


@bench({"size": ["smoke"], "cls": ["A"]}, rtol=1e-9)
def square(size: str, cls: str):
    return lambda: sum(i * i for i in range(10_000)), UNCHECKED


def test_the_name_says_subject_case_params_and_release():
    name = profiling.profile_name("bw2calc", "first_score", {"size": "ecoinvent", "cls": "IterativeLCA"}, "3.0.0")
    assert name == "bw2calc-first_score-size=ecoinvent-cls=IterativeLCA-3.0.0"


def test_a_profile_writes_html_and_speedscope(tmp_path: Path):
    html, scope = profiling.profile(square, {"size": "smoke", "cls": "A"}, "toy", tmp_path)
    assert [html.name, scope.name] == ["toy.html", "toy.speedscope.json"]
    assert "<html" in html.read_text()
    assert "speedscope" in json.loads(scope.read_text())["$schema"]


def test_wrong_parameters_stop_the_profile(tmp_path: Path):
    with pytest.raises(SystemExit, match="takes size, cls; got size"):
        profiling.profile(square, {"size": "smoke"}, "toy", tmp_path)
