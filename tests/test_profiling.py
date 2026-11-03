"""bwbench.profiling on a toy benchmark; no Brightway code runs here."""

import json
from pathlib import Path

import pytest

from bwbench import profiling
from bwbench.bench import UNCHECKED, bench


@bench({"size": ["smoke"], "cls": ["A"]}, rtol=1e-9)
def square(size: str, cls: str):
    return lambda: sum(i * i for i in range(10_000)), UNCHECKED


@bench({"groups": [100, 1000]})
def lookup(groups: int):
    if not isinstance(groups, int):
        raise TypeError(groups)
    return lambda: list(range(groups)), UNCHECKED


def test_the_name_says_subject_case_params_release_and_packages():
    params = {"size": "ecoinvent", "cls": "IterativeLCA"}
    name = profiling.profile_name("bw2calc", "first_score", params, "3.0.0", ["scikit-umfpack"])
    assert name == "bw2calc-first_score-size=ecoinvent-cls=IterativeLCA-3.0.0-with=scikit-umfpack"
    assert profiling.profile_name("bw2calc", "first_score", params, "3.1.0", []).endswith("-3.1.0")


def test_values_take_the_declared_type_and_size_is_only_a_parameter(tmp_path: Path):
    params = profiling.typed(lookup, profiling.parse_params(["groups=10000"]))
    assert params == {"groups": 10000}
    assert profiling.profile(lookup, params, "toy", tmp_path)[0].name == "toy.html"
    # A size outside the knob's smoke default still goes through: a profile wants a full size.
    assert profiling.typed(square, {"size": "ecoinvent", "cls": "A"}) == {"size": "ecoinvent", "cls": "A"}


@pytest.mark.parametrize("args", [["groups"], ["=3"], ["groups=1", "groups=2"]])
def test_malformed_parameters_stop_the_profile(args: list[str]):
    with pytest.raises(SystemExit, match="NAME=VALUE"):
        profiling.parse_params(args)


def test_a_profile_writes_html_and_speedscope(tmp_path: Path):
    html, scope = profiling.profile(square, {"size": "smoke", "cls": "A"}, "toy", tmp_path)
    assert [html.name, scope.name] == ["toy.html", "toy.speedscope.json"]
    assert "<html" in html.read_text()
    assert "speedscope" in json.loads(scope.read_text())["$schema"]


def test_wrong_parameters_stop_the_profile():
    with pytest.raises(SystemExit, match="takes size, cls; got size"):
        profiling.typed(square, {"size": "smoke"})


def test_a_value_of_the_wrong_type_stops_the_profile():
    with pytest.raises(SystemExit, match="groups=abc: lookup takes int values"):
        profiling.typed(lookup, {"groups": "abc"})


torn_down: list[str] = []


@bench({"size": ["smoke"]}, rtol=1e-9)
def wrong(size: str):
    yield (lambda: 1.0), 2.0
    torn_down.append(size)


def test_a_wrong_answer_writes_no_profile_and_still_tears_down(tmp_path: Path):
    torn_down.clear()
    with pytest.raises(Exception, match="wrong"):
        profiling.profile(wrong, {"size": "smoke"}, "toy", tmp_path)
    assert torn_down == ["smoke"]
    assert list(tmp_path.iterdir()) == []
