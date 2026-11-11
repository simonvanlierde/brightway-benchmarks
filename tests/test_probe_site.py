"""scripts/probe_site.py with `gh` stubbed out: which python-probe result it keeps for each cell."""

import importlib
import io
import json
import zipfile
from datetime import date
from pathlib import Path
from types import ModuleType

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
TODAY = date(2026, 11, 11)
GOOD = [{"step": "install x", "ok": True, "error": "e" * 900}]


def zipped(probe: dict) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        z.writestr("probe.json", json.dumps(probe))
    return buffer.getvalue()


def artifact(id_: int, name: str, created: str, *, branch: str = "main") -> dict:
    run = {"id": id_ * 100, "head_branch": branch, "repository_id": 100, "head_repository_id": 100}
    return {"id": id_, "name": name, "created_at": created, "expired": False, "workflow_run": run}


@pytest.fixture
def probe_site(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    monkeypatch.syspath_prepend(str(SCRIPTS))
    return importlib.import_module("probe_site")


def run(
    module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    artifacts: list[dict],
    probes: dict[int, dict] | None = None,
    *,
    broken: bool = False,
) -> list[dict] | None:
    """The cells main() writes, or None when it wrote no file."""
    zips = {a["id"]: zipped((probes or {}).get(a["id"], {"steps": GOOD})) for a in artifacts}

    def gh(*args: str) -> bytes:
        path = args[-1] if "--jq" not in args else args[1]
        if broken:
            msg = "HTTP 502"
            raise RuntimeError(msg)
        if "/artifacts/" in path:
            return zips[int(path.split("/artifacts/")[1].split("/")[0])]
        if "/actions/runs/" in path:
            return json.dumps(
                {
                    "workflow_id": 11,
                    "path": ".github/workflows/python-probe.yml",
                    "event": "schedule",
                    "head_branch": "main",
                    "repository": {"id": 100},
                    "head_repository": {"id": 100},
                }
            ).encode()
        if path.endswith("python-probe.yml"):
            return b'{"id": 11}'
        if "/artifacts" in path:
            return "\n".join(map(json.dumps, artifacts)).encode()
        return b'{"id": 100}'

    monkeypatch.setattr(module, "gh", gh)
    monkeypatch.setattr(importlib.import_module("compat_site"), "gh", gh)  # GreenArtifacts asks through its own
    out = tmp_path / "compat" / "python-probe.json"
    module.main(out, TODAY)
    return json.loads(out.read_text())["cells"] if out.exists() else None


def test_keeps_each_cells_newest_trusted_result_and_cuts_long_errors(
    probe_site: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    newest_first = [
        artifact(3, "python-probe-3.15-ubuntu-latest", "2026-11-10"),
        artifact(2, "compat-green-latest-3.12-ubuntu-latest", "2026-11-10"),
        artifact(1, "python-probe-3.15-ubuntu-latest", "2026-11-03"),
        artifact(4, "python-probe-3.9-ubuntu-latest", "2026-11-09", branch="feature"),
        artifact(5, "python-probe-3.10-ubuntu-latest", "2026-11-09"),
    ]
    cells = run(probe_site, monkeypatch, tmp_path, newest_first)
    assert cells
    assert [(c["python"], c["os"], c["date"]) for c in cells] == [
        ("3.10", "ubuntu-latest", "2026-11-09"),
        ("3.15", "ubuntu-latest", "2026-11-10"),
    ]
    assert cells[1]["run"].endswith("/actions/runs/300")
    error = cells[1]["steps"][0]["error"]
    assert len(error) == probe_site.ERROR_HEAD + len(" … ") + probe_site.ERROR_TAIL


def test_a_result_older_than_its_cadence_is_left_out(
    probe_site: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    artifacts = [
        artifact(1, "python-probe-3.15-ubuntu-latest", "2026-11-08"),  # 3 days: still current
        artifact(2, "python-probe-3.14-ubuntu-latest", "2026-11-07"),  # 4 days: a daily job stopped
        artifact(3, "python-probe-3.10-ubuntu-latest", "2026-11-02"),  # 9 days: a Monday job's limit
        artifact(4, "python-probe-3.9-ubuntu-latest", "2026-11-01"),  # 10 days
    ]
    cells = run(probe_site, monkeypatch, tmp_path, artifacts)
    assert cells
    assert [c["python"] for c in cells] == ["3.10", "3.15"]


def test_a_malformed_result_is_left_out_with_a_warning(
    probe_site: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    artifacts = [
        artifact(1, "python-probe-3.15-ubuntu-latest", "2026-11-10"),
        artifact(2, "python-probe-3.14-ubuntu-latest", "2026-11-10"),
    ]
    cells = run(probe_site, monkeypatch, tmp_path, artifacts, {1: {"steps": [{"ok": True}]}})
    assert cells
    assert [c["python"] for c in cells] == ["3.14"]
    assert "::warning::" in capsys.readouterr().out


def test_a_github_error_warns_and_writes_no_file(
    probe_site: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    cells = run(
        probe_site, monkeypatch, tmp_path, [artifact(1, "python-probe-3.15-ubuntu-latest", "2026-11-10")], broken=True
    )
    assert cells is None
    printed = capsys.readouterr().out
    assert "::warning::" in printed
    assert "HTTP 502" in printed


def test_no_current_result_warns_and_writes_no_file(
    probe_site: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    cells = run(probe_site, monkeypatch, tmp_path, [artifact(1, "python-probe-3.15-ubuntu-latest", "2026-10-01")])
    assert cells is None
    assert "::warning::" in capsys.readouterr().out


def test_a_long_error_keeps_the_end_uv_puts_its_cause_in(probe_site: ModuleType, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.syspath_prepend(str(SCRIPTS))
    export_guidance = importlib.import_module("export_guidance")
    chain = "Because of a long chain of reasons, " * 18
    error = f"error: No solution found: {chain}so bw-timex>=0.3.0 cannot be used."
    assert len(error) > 650
    [step] = probe_site.trim({"steps": [{"step": "install bw_timex", "ok": False, "error": error}]})
    assert step["error"].startswith("error: No solution found: ")
    assert step["error"].endswith("bw-timex>=0.3.0 cannot be used.")
    assert export_guidance.reason(step["error"]).endswith("bw-timex>=0.3.0 cannot be used.")
