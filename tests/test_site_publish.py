"""The Pages copy step must publish complete viewer metadata and assets."""

import os
import subprocess
import textwrap
from pathlib import Path

import pytest

REPOSITORY = Path(__file__).resolve().parents[1]
ASSETS = ("favicon.svg", "favicon.ico", "apple-touch-icon.png", "og.png")


def copy_viewer(tmp_path: Path, missing: str | None = None) -> subprocess.CompletedProcess[str]:
    dist = tmp_path / "ui" / "dist"
    (dist / "about").mkdir(parents=True)
    (dist / "stories" / "solver-choice").mkdir(parents=True)
    for name in ("index.html", "about/index.html", "stories/solver-choice/index.html", "sitemap.xml", *ASSETS):
        if name != missing:
            (dist / name).write_text(f"fixture: {name}")
    workflow = (REPOSITORY / ".github/workflows/site.yml").read_text()
    start = workflow.index("          mkdir -p site/ui\n")
    end = workflow.index("          uvx ", start)
    commands = textwrap.dedent(workflow[start:end])
    return subprocess.run(
        ["/bin/bash", "-e", "-c", commands],
        cwd=tmp_path,
        env={"PATH": os.defpath, "LANG": "C.UTF-8"},
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.parametrize("missing", ASSETS)
def test_publish_fails_when_a_required_preview_asset_is_missing(tmp_path: Path, missing: str) -> None:
    result = copy_viewer(tmp_path, missing)
    assert result.returncode != 0, f"Pages silently omitted {missing}"


def test_publish_copies_complete_preview_assets_and_static_pages(tmp_path: Path) -> None:
    result = copy_viewer(tmp_path)
    assert result.returncode == 0, result.stderr
    for name in ASSETS:
        for prefix in ("site", "site/ui"):
            assert (tmp_path / prefix / name).read_text() == f"fixture: {name}"
    for name in ("index.html", "about/index.html", "stories/solver-choice/index.html", "sitemap.xml"):
        assert (tmp_path / "site" / name).read_text() == f"fixture: {name}"
