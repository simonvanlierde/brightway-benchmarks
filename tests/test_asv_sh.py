"""scripts/asv.sh's config step: which environments asv gets, with uvx stubbed out."""

import hashlib
import importlib.util
import json
import platform
import shutil
import subprocess
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
CONF = {
    "results_dir": "../results",
    "matrix": {"req": {"numpy": ["2.5.3"]}},
    "include": [
        {"python": "3.12", "req": {"numpy": "2.5.3", "pypardiso": ""}},
        {"python": "3.12", "req": {"numpy": "2.5.3", "scikit-umfpack": ""}},
        {"python": "3.12", "req": {"numpy": "2.5.3", "pyklu": "0.2.0"}, "env": {"BWBENCH_SOLVER": "klu"}},
        {"python": "3.12", "req": {"numpy": "2.5.3", "scikit-umfpack": ""}, "env": {"BWBENCH_SOLVER": "umfpack-T"}},
    ],
}


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A scratch repo with asv.sh, two subject configs and uvx and uv stubs that do nothing."""
    (tmp_path / "scripts").mkdir()
    shutil.copy(REPO / "scripts" / "asv.sh", tmp_path / "scripts")
    (tmp_path / "asv").mkdir()
    (tmp_path / ".asv").mkdir()
    (tmp_path / "asv" / "solvers.json").write_text(json.dumps(CONF))
    (tmp_path / "asv" / "plain.json").write_text(json.dumps({"results_dir": "../results", "matrix": {"req": {}}}))
    for s in ("solvers", "plain"):
        (tmp_path / "asv" / f"{s}.stack.txt").write_text("numpy==2.5.3\n")
    (tmp_path / "stub").mkdir()
    # Also logs BWBENCH_SOLVER, which asv would hand on to every environment's benchmarks.
    (tmp_path / "stub" / "uvx").write_text('#!/bin/sh\necho "$@" "solver=${BWBENCH_SOLVER-unset}" >>"$0.log"\nexit 0\n')
    (tmp_path / "stub" / "uvx").chmod(0o755)
    (tmp_path / "stub" / "uv").write_text('#!/bin/sh\necho "$@" >>"$0.log"\nexit 0\n')
    (tmp_path / "stub" / "uv").chmod(0o755)
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


def test_patched_solvers_run_only_when_named(repo: Path):
    out, conf = config(repo, "solvers")  # the default set
    assert out.returncode == 0, out.stderr
    assert all("BWBENCH_SOLVER" not in e["env"] for e in conf["include"])
    out, conf = config(repo, "solvers", BWBENCH_SOLVERS="umfpack-T")
    assert out.returncode == 0, out.stderr
    # Its scikit-umfpack does not make it the umfpack environment, nor the reverse.
    assert [e["env"]["BWBENCH_SOLVER"] for e in conf["include"]] == ["umfpack-T"]
    if platform.machine() == "x86_64":
        _, conf = config(repo, "solvers", BWBENCH_SOLVERS="klu,umfpack")
        assert [list(e["req"])[-1] for e in conf["include"]] == ["scikit-umfpack", "pyklu"]
    else:
        out, _ = config(repo, "solvers", BWBENCH_SOLVERS="klu")
        assert "klu has wheels for x86_64 only" in out.stderr


def test_an_entry_keeps_its_env_and_gets_the_stack(repo: Path):
    """The env names asv's environment, so the entries without one must come out as before."""
    _, conf = config(repo, "solvers", BWBENCH_SOLVERS="superlu,umfpack,umfpack-T")
    stack = conf["matrix"]["env"]["BWBENCH_STACK"][0]
    assert [e["env"] for e in conf["include"]] == [
        {"BWBENCH_STACK": stack},
        {"BWBENCH_SOLVER": "umfpack-T", "BWBENCH_STACK": stack},
    ]


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


def add_env(repo: Path, name: str, *, conda: bool = False, stack: str | None = None) -> None:
    """A built environment of plain, whose python prints numpy==2.5.3, on the current stack unless named."""
    env = repo / ".asv" / "env" / "plain" / name
    (env / "bin").mkdir(parents=True)
    if conda:
        (env / "conda-meta").mkdir()
        (env / "conda-meta" / "libblas-3.11.0-1_h1ea3ea9_openblas.json").write_text("{}")
    stack = stack or hashlib.sha256((repo / "asv" / "plain.stack.txt").read_bytes()).hexdigest()[:8]
    # As asv writes it, indented.
    info = {"build_env_vars": {"BWBENCH_STACK": stack}, "tool_name": "rattler" if conda else "uv"}
    (env / "asv-env-info.json").write_text(json.dumps(info, indent=4))
    (env / "bin" / "python").write_text("#!/bin/sh\necho numpy==2.5.3\n")
    (env / "bin" / "python").chmod(0o755)


def run_with_env(repo: Path, *, conda: bool) -> subprocess.CompletedProcess:
    """`asv.sh plain run` with one built environment, abc."""
    add_env(repo, "abc", conda=conda)
    return subprocess.run(
        ["/bin/sh", "scripts/asv.sh", "plain", "run"],
        cwd=repo,
        env={"PATH": f"{repo / 'stub'}:/usr/bin:/bin", "HOME": str(repo), "BWBENCH_MACHINE": "m"},
        capture_output=True,
        text=True,
        check=False,
    )


def test_a_conda_environment_records_its_conda_packages(repo: Path):
    """A rattler environment lists conda-meta (build strings show the BLAS) and gets no PyPI lock."""
    out = run_with_env(repo, conda=True)
    assert out.returncode == 0, out.stderr
    versions = (repo / "results" / "m" / "versions-abc.txt").read_text()
    assert "libblas-3.11.0-1_h1ea3ea9_openblas" in versions
    assert "numpy==2.5.3" in versions
    assert not (repo / "results" / "m" / "pylock.abc.toml").exists()
    assert "pip compile" not in (repo / "stub" / "uv.log").read_text()


def test_a_pypi_environment_gets_only_its_lock(repo: Path):
    """A uv environment is described by its pylock file: no versions file beside it."""
    out = run_with_env(repo, conda=False)
    assert out.returncode == 0, out.stderr
    assert not (repo / "results" / "m" / "versions-abc.txt").exists()
    assert "-o .asv/../results/m/pylock.abc.toml" in (repo / "stub" / "uv.log").read_text()


def test_asv_can_build_rattler_environments(repo: Path):
    config(repo, "plain")
    assert "--with py-rattler==" in (repo / "stub" / "uvx.log").read_text()


def test_a_stray_solver_does_not_reach_asv(repo: Path):
    # Only the klu and umfpack-T entries may set it (in their own env), not the caller's shell.
    out, _ = config(repo, "solvers", BWBENCH_SOLVERS="umfpack", BWBENCH_SOLVER="umfpack-T")
    assert out.returncode == 0, out.stderr
    assert "solver=unset" in (repo / "stub" / "uvx.log").read_text()


@pytest.mark.parametrize("conda", [False, True])
def test_an_environment_of_an_older_stack_gets_no_lock(repo: Path, conda: bool):  # noqa: FBT001
    """Asv leaves the folders of earlier stacks in .asv/env; their packages are not what ran."""
    add_env(repo, "old", conda=conda, stack="0ld57ack")
    out = run_with_env(repo, conda=conda)
    assert out.returncode == 0, out.stderr
    written = sorted(p.name for p in (repo / "results" / "m").iterdir() if not p.name.startswith("bwbench-run-"))
    assert written == (["versions-abc.txt"] if conda else [])
    assert "pylock.old.toml" not in (repo / "stub" / "uv.log").read_text()


def test_each_result_keeps_the_commit_that_wrote_it(repo: Path):
    """Two runs at different bwbench commits: the crate credits each result to its own run."""
    (repo / "asv" / "plain.json").write_text(json.dumps({"results_dir": "../results/plain", "matrix": {"req": {}}}))
    # asv writes one result file per run, named after RESULT.
    (repo / "stub" / "uvx").write_text(
        '#!/bin/sh\ncase "$*" in *" run "*) mkdir -p results/plain/m\n'
        'echo "$RESULT" >"results/plain/m/$RESULT.json" ;; esac\n'
    )
    env = {"PATH": f"{repo / 'stub'}:/usr/bin:/bin", "HOME": str(repo), "BWBENCH_MACHINE": "m"}
    for result, commit in (("first", "a" * 40), ("second", "b" * 40)):
        out = subprocess.run(
            ["/bin/sh", "scripts/asv.sh", "plain", "run"],
            cwd=repo,
            env=env | {"RESULT": result, "BWBENCH_COMMIT": commit},
            capture_output=True,
            text=True,
            check=False,
        )
        assert out.returncode == 0, out.stderr
        time.sleep(1)  # records are named by the second
    spec = importlib.util.spec_from_file_location("run_crate", REPO / "scripts" / "run_crate.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    graph = {e["@id"]: e for e in module.crate(repo / "results")["@graph"]}
    assert [r["@id"] for r in graph[f"#run-{'a' * 40}"]["result"]][-1] == "plain/m/first.json"
    assert [r["@id"] for r in graph[f"#run-{'b' * 40}"]["result"]][-1] == "plain/m/second.json"
    assert graph[f"{module.REPO}/tree/{'b' * 40}"]["version"] == "b" * 40
