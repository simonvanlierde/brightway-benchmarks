"""What a contributor's `uvx ... bwbench compare` installs, and the checks a contributed file must pass."""

import json
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from bwbench import compare
from bwbench.ratios import HOST_LIKE, USER_FOLDER, contribution_problems

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def wheel(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("dist")
    subprocess.run(["uv", "build", "--wheel", "--quiet", "-o", str(out), str(ROOT)], check=True)  # noqa: S607
    return next(out.glob("*.whl"))


def test_the_wheel_carries_the_cases_compare_times(wheel: Path):
    names = set(zipfile.ZipFile(wheel).namelist())
    for case in (compare.FIRST_SCORE[0], compare.WRITE[0]):
        module = case.split(".")[0]
        assert any(n.startswith("bwbench/cases/bench_") and n.endswith(f"/{module}.py") for n in names), module
    assert "bwbench/ratios.schema.json" in names


def test_installed_timecase_finds_the_packaged_cases(wheel: Path, tmp_path: Path):
    zipfile.ZipFile(wheel).extractall(tmp_path)
    code = "import sys; from bwbench.timecase import BENCHMARKS; print(BENCHMARKS)"
    proc = subprocess.run(
        [sys.executable, "-I", "-c", f"import sys; sys.path.insert(0, {str(tmp_path)!r}); {code}"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert Path(proc.stdout.strip()) == tmp_path / "bwbench" / "cases"


def test_stage_gives_the_arms_this_package_and_the_cases_only(tmp_path: Path):
    src = compare.stage(tmp_path)
    assert sorted(p.name for p in src.iterdir()) == ["bwbench"]
    assert (src / "bwbench" / "timecase.py").is_file()
    assert (src / "bwbench" / "cases" / "bench_bw2calc" / "bench_lca.py").is_file()
    assert not list(src.rglob("__pycache__"))
    assert compare.stage(tmp_path) == src  # a rerun in the same --work folder


def contributed(tmp_path: Path, doc: dict, rel: str = "ratios/contributed/apple-m3-pro/2026-11-14.json") -> Path:
    path = tmp_path / rel
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(doc), encoding="utf-8")
    return path


GOOD = {"tier": "contributed", "machine": "Apple M3 Pro", "created": "2026-11-14T09:30:00Z", "comparisons": []}


def test_a_contribution_in_its_place_passes(tmp_path: Path):
    assert contribution_problems(contributed(tmp_path, GOOD), GOOD) == []


@pytest.mark.parametrize(
    ("change", "rel", "expect"),
    [
        ({"tier": "hosted"}, None, "tier"),
        ({"tier": "reference"}, None, "tier"),
        ({"machine": "Other laptop"}, None, "other-laptop"),
        ({"created": "2026-11-13T23:59:00Z"}, None, "2026-11-13"),
        ({}, "ratios/contributed/apple-m3-pro/latest.json", "ratios/contributed/<machine>/<YYYY-MM-DD>.json"),
        ({}, "ratios/hosted/apple-m3-pro/2026-11-14.json", "ratios/contributed/<machine>/<YYYY-MM-DD>.json"),
        (
            {"machine": "adas-macbook-pro.local"},
            "ratios/contributed/adas-macbook-pro-local/2026-11-14.json",
            "host",
        ),
        ({"machine": "Ada's MacBook Pro"}, "ratios/contributed/ada-s-macbook-pro/2026-11-14.json", "host"),
        ({"machine": "DESKTOP-4F2K9QX"}, "ratios/contributed/desktop-4f2k9qx/2026-11-14.json", "host"),
        ({"comparisons": [{"missing": "no file /Users/someone/x"}]}, None, "user folder"),
        ({"comparisons": [{"missing": "no file C:\\Users\\someone\\x"}]}, None, "user folder"),
        ({"comparisons": [{"missing": "no file /home/someone/x"}]}, None, "user folder"),
    ],
)
def test_a_contribution_is_refused(tmp_path: Path, change: dict, rel: str | None, expect: str):
    doc = GOOD | change
    path = contributed(tmp_path, doc, *([rel] if rel else []))
    found = contribution_problems(path, doc)
    assert any(expect in p for p in found), found


def test_a_large_or_linked_contribution_is_refused(tmp_path: Path):
    path = contributed(tmp_path, GOOD | {"pad": "x" * 300_000})
    assert any("KiB" in p for p in contribution_problems(path, GOOD))
    link = path.with_name("2026-11-15.json")
    link.symlink_to(path)
    assert any(
        "not a regular file" in p for p in contribution_problems(link, GOOD | {"created": "2026-11-15T00:00:00Z"})
    )


def test_validate_contribution_flag_runs_the_extra_checks(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    path = contributed(tmp_path, GOOD | {"tier": "hosted"})
    assert compare.main(["validate", "--contribution", str(path)]) == 1
    assert "tier" in capsys.readouterr().err


def test_tail_hides_the_home_folder():
    proc = subprocess.CompletedProcess([], 1, "", f"error: {Path.home() / 'x'} failed")
    assert str(Path.home()) not in compare._tail(proc)  # noqa: SLF001


def test_stage_leaves_a_checkout_folder_alone(tmp_path: Path):
    """`bwbench compare --work .` from a checkout must not replace the checkout's own package."""
    mine = tmp_path / "src" / "bwbench"
    mine.mkdir(parents=True)
    (mine / "edited.py").write_text("x = 1\n", encoding="utf-8")
    compare.stage(tmp_path)
    assert (mine / "edited.py").read_text(encoding="utf-8") == "x = 1\n"


def test_stage_refuses_to_overwrite_the_package_it_runs_from(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    staged = compare.stage(tmp_path) / "bwbench"
    monkeypatch.setattr(compare, "PACKAGE", staged)
    with pytest.raises(RuntimeError, match="inside"):
        compare.stage(tmp_path)
    assert (staged / "timecase.py").is_file()


@pytest.mark.parametrize(
    ("home", "text", "gone"),
    [
        (None, "C:\\Users\\ADALIN~1\\AppData\\Local\\Temp\\x failed", "ADALIN"),
        (None, "C:/Users/adalovelace/x failed", "adalovelace"),
        (None, "c:\\\\users\\\\adalovelace\\\\x failed", "adalovelace"),
        (None, "/home/adalovelace/x failed", "adalovelace"),
        (None, "/Users/adalovelace/x failed", "adalovelace"),
        ("/srv/AdaLovelace", "/srv/adalovelace/x failed", "adalovelace"),
    ],
)
def test_tail_hides_user_folders(monkeypatch: pytest.MonkeyPatch, home: str | None, text: str, gone: str):
    if home is not None:
        monkeypatch.setattr(Path, "home", lambda: Path(home))
    out = compare._tail(subprocess.CompletedProcess([], 1, "", text))  # noqa: SLF001
    assert gone.lower() not in out.lower()
    assert "~" in out
    assert not USER_FOLDER.search(json.dumps(out))


def test_tail_keeps_paths_when_home_is_the_root(monkeypatch: pytest.MonkeyPatch):
    """`docker run --user` with no passwd entry gives HOME=/."""
    monkeypatch.setattr(Path, "home", lambda: Path("/"))
    proc = subprocess.CompletedProcess([], 1, "", "/usr/bin/python: /opt/x failed")
    assert compare._tail(proc) == "/usr/bin/python: /opt/x failed"  # noqa: SLF001


@pytest.mark.parametrize(
    ("text", "user"),
    [
        ("C:/Users/ada/x", True),
        ("C:\\\\Users\\\\ada\\\\x", True),
        ("/root/.cache/uv", True),
        ("/home/ada/x", True),
        ("/Users/ada/x", True),
        ("/home/linuxbrew/.linuxbrew/bin/python3", False),
        ("/Users/Shared/bw/x", False),
        ("~/.cache/uv", False),
    ],
)
def test_user_folder_matches_what_redaction_leaves(text: str, *, user: bool):
    assert bool(USER_FOLDER.search(text)) is user


@pytest.mark.parametrize(
    "machine",
    [
        "Ada's MacBook Pro",
        "Ada\u2019s MacBook Pro",
        "Adas-MacBook-Pro",
        "Adas-iMac",
        "ada-ThinkPad-X1-Carbon-Gen-9",
        "ada-XPS-15-9520",
        "adas-macbook-pro.local",
        "ada.example.com",
        "DESKTOP-4F2K9QX",
    ],
)
def test_host_names_are_refused(machine: str):
    assert HOST_LIKE.search(machine)


@pytest.mark.parametrize(
    "machine",
    ["Apple M3 Pro", "ubuntu-24.04", "m2.max", "ryzen-5.5600X", "Lenovo-ThinkPad-X1", "Intel Xeon machine"],
)
def test_machine_labels_pass(machine: str):
    assert not HOST_LIKE.search(machine)


def test_a_label_without_ascii_letters_or_digits_is_refused(capsys: pytest.CaptureFixture[str]):
    with pytest.raises(SystemExit) as e:
        compare.main(["compare", "-o", "x.json", "--machine", "\u82f9\u679c"])
    assert e.value.code == 2
    assert "ASCII letters or digits" in capsys.readouterr().err
