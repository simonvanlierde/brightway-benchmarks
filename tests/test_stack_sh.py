"""scripts/stack.sh: the fixed stack is resolved at in-box.sh's cutoff and says so, with uv stubbed out."""

import json
import shutil
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def stack(tmp_path: Path, exclude_newer: str) -> subprocess.CompletedProcess:
    (tmp_path / "scripts").mkdir(exist_ok=True)
    for script in ("stack.sh", "asv_conf.py", "in-box.sh"):
        shutil.copy(REPO / "scripts" / script, tmp_path / "scripts")
    (tmp_path / "asv").mkdir(exist_ok=True)
    (tmp_path / "asv" / "s.json").write_text(json.dumps({"matrix": {"req": {"numpy": ["2.5.3"]}}}))
    (tmp_path / "asv" / "s.hashes").write_text("v1.0\n")
    stub = tmp_path / "stub"
    stub.mkdir(exist_ok=True)
    (stub / "uv").write_text("#!/bin/sh\nprintf 'numpy==2.5.3\\ns==1.0\\n'\n")
    (stub / "uv").chmod(0o755)
    return subprocess.run(
        ["/bin/sh", "scripts/stack.sh", "s"],
        cwd=tmp_path,
        env={"PATH": f"{stub}:/usr/bin:/bin", "UV_EXCLUDE_NEWER": exclude_newer},
        capture_output=True,
        text=True,
        check=False,
    )


def test_the_stack_names_the_cutoff_it_was_resolved_at(tmp_path: Path):
    cutoff = next(
        line for line in (REPO / "scripts" / "in-box.sh").read_text().splitlines() if line.startswith("cutoff=")
    )
    out = stack(tmp_path, cutoff.removeprefix("cutoff="))
    assert out.returncode == 0, out.stderr
    assert (tmp_path / ".asv" / "stack" / "s.txt").read_text() == f"# {cutoff.replace('=', ' ')}\nnumpy==2.5.3\n"


def test_another_cutoff_is_refused(tmp_path: Path):
    out = stack(tmp_path, "2030-01-01T00:00:00Z")
    assert out.returncode == 1
    assert "not in-box.sh's cutoff" in out.stderr
    assert not (tmp_path / ".asv" / "stack" / "s.txt").exists()
