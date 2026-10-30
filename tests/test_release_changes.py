"""scripts/release_changes.py on two hand-written asv result files per environment."""

import hashlib
import importlib
import json
import shutil
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

GIT = shutil.which("git") or "git"
SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
STACK = "-BWBENCH_STACKaaaa1111"
PARAMS = [["'ecoinvent'"], ["'LCA'", "'IterativeLCA'"]]
UNITS = {  # as in asv's benchmarks.json
    "bench_lca.SingleScore.time_first_score": "seconds",
    "bench_lca.SingleScore.peakmem_first_score": "bytes",
    "bench_lca.SingleScore.track_relative_error": "unit",
}


def result(commit: str, env: str, first: list, peak: list, error: list) -> dict:
    """An asv result file: commit, environment, and one value per parameter set of each case."""
    return {
        "commit_hash": commit + "0" * 32,
        "env_name": env,
        "result_columns": ["result", "params"],
        "results": {name: [values, PARAMS] for name, values in zip(UNITS, [first, peak, error], strict=True)},
    }


@pytest.fixture
def module(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.syspath_prepend(str(SCRIPTS))
    # Imported by name, not from its file, so that its own `from release_report import sha` resolves.
    release_changes = importlib.import_module("release_changes")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(release_changes, "sha", lambda _mirror, tag: f"{tag:0<8}"[:8])  # no asv mirror here
    layout(tmp_path, "1.0\n2.0\n3.0\n")
    return release_changes


def layout(tmp_path: Path, hashes: str) -> None:
    """asv/s.hashes and an empty results/s/ for one machine, as `just bench` leaves them."""
    (tmp_path / "asv").mkdir()
    (tmp_path / "asv" / "s.hashes").write_text(hashes)
    (tmp_path / "results" / "s" / "m").mkdir(parents=True)
    (tmp_path / "results" / "s" / "m" / "machine.json").write_text("{}")
    (tmp_path / "results" / "s" / "benchmarks.json").write_text(
        json.dumps({"version": 2} | {k: {"unit": u} for k, u in UNITS.items()})
    )


def write(tmp_path: Path, data: dict) -> None:
    path = tmp_path / "results" / "s" / "m" / f"{data['commit_hash'][:8]}-{data['env_name']}.json"
    path.write_text(json.dumps(data))


def test_lists_cases_that_moved_between_the_newest_two_releases(module: ModuleType, tmp_path: Path):
    env = "uv-py3.12-umfpack" + STACK
    # 1.0 is older than the pair compared, so its numbers must not show up.
    write(tmp_path, result("1.000000", env, [99.0, 99.0], [1e9, 1e9], [1e-15, 1e-15]))
    write(tmp_path, result("2.000000", env, [9.04, 45.0], [5e8, 5.9e8], [4e-15, 4e-15]))
    write(tmp_path, result("3.000000", env, [9.05, 9.05], [5e8, 5e8], [7e-15, 7e-15]))
    rows = module.changes(tmp_path / "results", "s")
    # LCA moved 0.1%, under the threshold; track_ cases count errors, not time, and are left out.
    assert [(c.env, c.old_tag, c.new_tag, c.stack_moved, c.case, c.params) for c in rows] == [
        ("m/uv-py3.12-umfpack", "2.0", "3.0", False, "SingleScore.peakmem_first_score", "'ecoinvent', 'IterativeLCA'"),
        ("m/uv-py3.12-umfpack", "2.0", "3.0", False, "SingleScore.time_first_score", "'ecoinvent', 'IterativeLCA'"),
    ]
    assert (rows[0].old, rows[0].new) == ("590 MB", "500 MB")
    assert (rows[1].old, rows[1].new, rows[1].ratio) == ("45 s", "9.05 s", pytest.approx(9.05 / 45.0))


def test_a_failed_case_that_runs_again_is_listed(module: ModuleType, tmp_path: Path):
    env = "uv-py3.12" + STACK
    write(tmp_path, result("2.000000", env, [27.6, None], [5e8, 5e8], [0.0, 0.0]))
    write(tmp_path, result("3.000000", env, [27.7, 27.9], [5e8, float("nan")], [0.0, 0.0]))
    rows = module.changes(tmp_path / "results", "s")
    assert [(c.case, c.old, c.new, c.ratio) for c in rows] == [
        ("SingleScore.peakmem_first_score", "500 MB", "skipped", None),
        ("SingleScore.time_first_score", "failed", "27.9 s", None),
    ]


def test_a_case_new_in_the_latest_release_is_not_a_change(module: ModuleType, tmp_path: Path):
    env = "uv-py3.12" + STACK
    write(tmp_path, result("2.000000", env, [27.6, float("nan")], [5e8, 5e8], [0.0, 0.0]))
    write(tmp_path, result("3.000000", env, [27.7, 27.9], [5e8, 5e8], [0.0, 0.0]))
    assert module.changes(tmp_path / "results", "s") == []


def test_flags_a_dependency_stack_that_moved_between_releases(module: ModuleType, tmp_path: Path):
    write(tmp_path, result("2.000000", "uv-py3.12-BWBENCH_STACKaaaa1111", [1.0, 1.0], [5e8, 5e8], [0.0, 0.0]))
    write(tmp_path, result("3.000000", "uv-py3.12-BWBENCH_STACKbbbb2222", [2.0, 1.0], [5e8, 5e8], [0.0, 0.0]))
    (row,) = module.changes(tmp_path / "results", "s")
    assert (row.env, row.old_tag, row.new_tag, row.stack_moved) == ("m/uv-py3.12", "2.0", "3.0", True)


def test_prefers_the_same_stack_and_then_the_current_one(module: ModuleType, tmp_path: Path):
    (tmp_path / "asv" / "s.stack.txt").write_text("numpy==2.5.3\n")
    current = "-BWBENCH_STACK" + hashlib.sha256(b"numpy==2.5.3\n").hexdigest()[:8]
    write(tmp_path, result("2.000000", "uv-py3.12-BWBENCH_STACK00000000", [1.0, 1.0], [5e8, 5e8], [0.0, 0.0]))
    write(tmp_path, result("2.000000", "uv-py3.12" + current, [2.0, 1.0], [5e8, 5e8], [0.0, 0.0]))
    write(tmp_path, result("3.000000", "uv-py3.12-BWBENCH_STACK00000000", [2.0, 1.0], [5e8, 5e8], [0.0, 0.0]))
    write(tmp_path, result("3.000000", "uv-py3.12" + current, [2.0, 1.0], [5e8, 5e8], [0.0, 0.0]))
    write(tmp_path, result("3.000000", "uv-py3.12-BWBENCH_STACKffffffff", [1.0, 1.0], [5e8, 5e8], [0.0, 0.0]))
    assert module.changes(tmp_path / "results", "s") == []


def test_cli_prints_a_markdown_table(tmp_path: Path):
    # A real asv mirror this time: a bare repository with the two releases as tags.
    mirror = tmp_path / ".asv" / "s"
    git = [GIT, "--git-dir", str(mirror)]
    subprocess.run([GIT, "init", "-q", "--bare", str(mirror)], check=True)
    tree = subprocess.run([*git, "mktree"], input="", capture_output=True, text=True, check=True).stdout.strip()
    shas = []
    for tag in ("2.0", "3.0"):
        parent = ["-p", shas[-1]] if shas else []
        commit = subprocess.run(
            [*git, "-c", "user.name=t", "-c", "user.email=t@t.test", "commit-tree", tree, *parent, "-m", tag],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        subprocess.run([*git, "tag", tag, commit], check=True)
        shas.append(commit)
    layout(tmp_path, "2.0\n3.0\n")
    env = "uv-py3.12" + STACK
    for commit, first in zip(shas, ([1.0, 1.0], [2.0, 1.0]), strict=True):
        data = result(commit[:8], env, first, [5e8, 5e8], [0.0, 0.0])
        data["commit_hash"] = commit
        write(tmp_path, data)
    run = subprocess.run(
        [sys.executable, SCRIPTS / "release_changes.py", "s", "results"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
    )
    lines = run.stdout.splitlines()
    assert lines[0] == "| environment | releases | case | parameters | old | new | new / old |"
    assert lines[2:] == [
        "| m/uv-py3.12 | 2.0 → 3.0 | SingleScore.time_first_score | 'ecoinvent', 'LCA' | 1 s | 2 s | 2.00 |"
    ]


def test_a_commit_listed_by_its_hash_needs_no_mirror(module: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture):
    commit = "106d62717c8867012fd9a91a46726c66c898f162"  # asv names its results by the hash itself
    (tmp_path / "asv" / "s.hashes").write_text(f"1.0\n{commit}\n")
    module.changes(tmp_path / "results", "s")
    assert "lacks" not in capsys.readouterr().err


def test_a_noisy_case_needs_a_bigger_move(module: ModuleType, tmp_path: Path):
    env = "uv-py3.12" + STACK
    old = result("2.000000", env, [10.0, 10.0], [5e8, 5e8], [0.0, 0.0])
    new = result("3.000000", env, [11.0, 11.0], [5e8, 5e8], [0.0, 0.0])
    for data, v in [(old, 10.0), (new, 11.0)]:
        data["result_columns"] = ["result", "params", "stats_q_25", "stats_q_75"]
        name = "bench_lca.SingleScore.time_first_score"
        # LCA's samples spread 4% around the value, IterativeLCA's 0.2%.
        data["results"][name] += [[v * 0.98, v * 0.999], [v * 1.02, v * 1.001]]
    write(tmp_path, old)
    write(tmp_path, new)
    rows = module.changes(tmp_path / "results", "s")
    # A 10% move: within three times LCA's 4% spread, beyond IterativeLCA's 2% floor.
    assert [r.params for r in rows] == ["'ecoinvent', 'IterativeLCA'"]


def test_the_noise_rule_has_a_floor(module: ModuleType):
    assert module.noise_threshold(None, None) == 0.02
    assert module.noise_threshold(0.001, None) == 0.02
    assert module.noise_threshold(0.01, 0.05) == pytest.approx(0.15)
