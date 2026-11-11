"""scripts/probe_site.py with `gh` stubbed out: which python-probe result it keeps for each cell."""

import importlib
import io
import json
import zipfile
from pathlib import Path
from types import ModuleType

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def zipped(steps: list[dict]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        z.writestr("probe.json", json.dumps({"steps": steps}))
    return buffer.getvalue()


def artifact(id_: int, name: str, created: str, *, branch: str = "main") -> dict:
    run = {"id": id_ * 100, "head_branch": branch, "repository_id": 100, "head_repository_id": 100}
    return {"id": id_, "name": name, "created_at": created, "expired": False, "workflow_run": run}


@pytest.fixture
def probe_site(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    monkeypatch.syspath_prepend(str(SCRIPTS))
    return importlib.import_module("probe_site")


def run(module: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, artifacts: list[dict]) -> list[dict]:
    zips = {a["id"]: zipped([{"step": "install x", "ok": True, "error": "e" * 900}]) for a in artifacts}

    def gh(*args: str) -> bytes:
        path = args[-1] if "--jq" not in args else args[1]
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
    module.main(out)
    return json.loads(out.read_text())["cells"]


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
    assert [(c["python"], c["os"], c["date"]) for c in cells] == [
        ("3.10", "ubuntu-latest", "2026-11-09"),
        ("3.15", "ubuntu-latest", "2026-11-10"),
    ]
    assert cells[1]["run"].endswith("/actions/runs/300")
    assert len(cells[1]["steps"][0]["error"]) == probe_site.ERROR
