"""scripts/minor_lines.py: the newest release of each minor line."""

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "minor_lines.py"
SHA = "a71ede783122e90b23df5cb1edbc9e17a1b74146"


def load():
    spec = importlib.util.spec_from_file_location("minor_lines", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_keeps_the_newest_of_each_minor_line_in_file_order():
    lines = ["2.0", "2.0.1", "2.0.2", "2.1", "2.2", "2.2.1", "3.0.0", "3.1.0"]
    assert load().minor_lines(lines) == ["2.0.2", "2.1", "2.2.1", "3.0.0", "3.1.0"]


def test_strips_a_v_prefix_and_orders_by_number_not_text():
    assert load().minor_lines(["v1.9.0", "v1.10.0", "v1.10.1"]) == ["v1.9.0", "v1.10.1"]


def test_bare_commit_is_always_kept():
    """An untagged release, such as bw_processing 1.3, must not replace the tagged line before it."""
    assert load().minor_lines(["1.1", "1.2", SHA, "1.4"]) == ["1.1", "1.2", SHA, "1.4"]


def test_every_hashes_file_selects_at_least_one_line():
    module = load()
    for path in (SCRIPT.parents[1] / "asv").glob("*.hashes"):
        assert module.minor_lines(path.read_text().split())
