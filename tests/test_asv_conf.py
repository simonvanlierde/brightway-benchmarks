"""scripts/asv_conf.py: what the shell scripts read from asv/SUBJECT.json."""

import importlib.util
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "asv_conf.py"
CONF = {
    "repo": "https://example.org/s.git",
    "matrix": {
        "req": {
            "numpy": ["2.5.3"],
            "pip+asv_runner": ["0.2.5"],
            "bw_processing": ["1.6", "git+https://example.org/bwp@abc"],
        }
    },
    "include": [{"python": "3.13", "req": {"numpy": "2.5.3", "scikit-umfpack": ""}}],
    "install_command": ["in-dir={env_dir} python -m pip install --no-deps threadpoolctl==3.7.0"],
}


def load():
    spec = importlib.util.spec_from_file_location("asv_conf", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "asv").mkdir()
    (tmp_path / "asv" / "s.json").write_text(json.dumps(CONF))
    (tmp_path / "asv" / "s.hashes").write_text("v1.0.0\nv1.2.0\n")
    (tmp_path / "asv" / "s.stack.txt").write_text("numpy==2.5.3\n")
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.mark.usefixtures("repo")
def test_stack_in_is_the_latest_release_and_the_matrix_pins():
    assert load().stack_in("s") == [
        "s==1.2.0",
        "numpy==2.5.3",
        "asv_runner==0.2.5",
        "bw_processing==1.6",
    ]


@pytest.mark.usefixtures("repo")
def test_drop_is_what_the_config_varies_and_the_subject():
    # numpy is in an include, but every environment pins it, so the stack keeps it.
    assert load().drop("s") == ["bw-processing", "s", "scikit-umfpack"]


@pytest.mark.usefixtures("repo")
def test_pins_are_the_matrix_and_install_command_pins():
    assert load().pins("s") == [
        "numpy==2.5.3",
        "bw_processing==1.6",
        "threadpoolctl==3.7.0",
    ]


@pytest.mark.usefixtures("repo")
def test_conf_refuses_an_unknown_solver():
    with pytest.raises(SystemExit, match="not cholmod"):
        load().conf("s", "m", "superlu,cholmod", "x86_64")


def test_every_subject_config_reads(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(REPO)
    module = load()
    for path in (REPO / "asv").glob("*.json"):
        s = path.stem
        assert module.stack_in(s)[0].startswith(f"{s}==")
        assert s.replace("_", "-") in module.drop(s)
        assert module.pins(s)
        assert module.load(s)["repo"].startswith("https://")
