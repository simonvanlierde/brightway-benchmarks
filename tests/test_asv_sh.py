"""scripts/asv.sh's config step: which environments asv gets, with uvx stubbed out."""

import json
import platform
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
CONF = {
    "results_dir": "../results",
    "matrix": {"req": {"numpy": ["2.5.3"]}},
    "include": [
        {"python": "3.12", "req": {"numpy": "2.5.3", "pypardiso": ""}},
        {"python": "3.12", "req": {"numpy": "2.5.3", "scikit-umfpack": ""}},
    ],
}


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A scratch repo with asv.sh, two subject configs and a uvx stub that does nothing."""
    (tmp_path / "scripts").mkdir()
    shutil.copy(REPO / "scripts" / "asv.sh", tmp_path / "scripts")
    (tmp_path / "asv").mkdir()
    (tmp_path / ".asv").mkdir()
    (tmp_path / "asv" / "solvers.json").write_text(json.dumps(CONF))
    (tmp_path / "asv" / "plain.json").write_text(json.dumps({"results_dir": "../results", "matrix": {"req": {}}}))
    for s in ("solvers", "plain"):
        (tmp_path / "asv" / f"{s}.stack.txt").write_text("numpy==2.5.3\n")
    (tmp_path / "stub").mkdir()
    (tmp_path / "stub" / "uvx").write_text('#!/bin/sh\necho "$@" >>"$0.log"\nexit 0\n')
    (tmp_path / "stub" / "uvx").chmod(0o755)
    # uname -n is the container hostname; -m stays real.
    (tmp_path / "stub" / "uname").write_text(
        '#!/bin/sh\n[ "$1" = -n ] && echo "${FAKE_HOSTNAME:-host-x-e0}" || exec /usr/bin/uname "$@"\n'
    )
    (tmp_path / "stub" / "uname").chmod(0o755)
    return tmp_path


def config(repo: Path, subject: str, **env: str) -> tuple[subprocess.CompletedProcess, dict]:
    out = subprocess.run(
        ["/bin/sh", "scripts/asv.sh", subject, "show"],
        cwd=repo,
        env={"PATH": f"{repo / 'stub'}:/usr/bin:/bin", "HOME": str(repo), "BWBENCH_MACHINE": "m", **env},
        capture_output=True,
        text=True,
        check=False,
    )
    local = repo / ".asv" / f".{subject}.local.json"
    return out, json.loads(local.read_text()) if local.exists() else {}


def test_solvers_filter_the_environments(repo: Path):
    out, conf = config(repo, "solvers", BWBENCH_SOLVERS="superlu,umfpack")
    assert out.returncode == 0, out.stderr
    assert [list(e["req"]) for e in conf["include"]] == [["numpy", "scikit-umfpack"]]
    assert "exclude" not in conf
    out, conf = config(repo, "solvers", BWBENCH_SOLVERS="umfpack")
    assert conf["exclude"] == [{"python": ".*"}]  # no superlu: the base environment goes


def test_a_misspelt_solver_is_refused(repo: Path):
    out, _ = config(repo, "solvers", BWBENCH_SOLVERS="superlu,pypardizo")
    assert out.returncode != 0
    assert "pypardizo" in out.stderr


@pytest.mark.skipif(platform.machine() != "x86_64", reason="pypardiso is refused off x86_64")
def test_the_stack_names_the_environment(repo: Path):
    _, before = config(repo, "plain", BWBENCH_SOLVERS="superlu")
    (repo / "asv" / "plain.stack.txt").write_text("numpy==2.5.2\n")
    _, after = config(repo, "plain", BWBENCH_SOLVERS="superlu")
    (stamp,) = before["matrix"]["env"]["BWBENCH_STACK"]
    assert [stamp] != after["matrix"]["env"]["BWBENCH_STACK"]
    _, solvers = config(repo, "solvers", BWBENCH_SOLVERS="superlu,pypardiso")
    assert all(e["env"]["BWBENCH_STACK"] == stamp for e in solvers["include"])


@pytest.mark.parametrize(
    ("hostname", "machine"),
    [("host-x-e0", "box-e0"), ("host-x-p1-quiet", "box-p1-quiet"), ("host-x-box", "box"), ("host-x", "box")],
)
def test_the_default_machine_leaves_out_the_host_name(repo: Path, hostname: str, machine: str):
    env = {"PATH": f"{repo / 'stub'}:/usr/bin:/bin", "HOME": str(repo), "FAKE_HOSTNAME": hostname}
    out = subprocess.run(
        ["/bin/sh", "scripts/asv.sh", "plain", "show"], cwd=repo, env=env, capture_output=True, text=True, check=False
    )
    assert out.returncode == 0, out.stderr
    assert f"--machine {machine} " in (repo / "stub" / "uvx.log").read_text()


def test_an_explicit_machine_wins(repo: Path):
    config(repo, "plain", FAKE_HOSTNAME="host-x-e0")
    assert "--machine m " in (repo / "stub" / "uvx.log").read_text()
