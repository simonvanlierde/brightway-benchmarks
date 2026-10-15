"""scripts/site_index.py on a site folder with one asv subject and one stray folder."""

import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "site_index.py"


def test_links_each_built_subject_with_its_description(tmp_path: Path):
    (tmp_path / "bw2calc").mkdir()
    (tmp_path / "bw2calc" / "index.html").write_text("")
    (tmp_path / "<odd>").mkdir()
    (tmp_path / "<odd>" / "index.html").write_text("")
    (tmp_path / "empty").mkdir()  # no index.html: not a built subject
    subprocess.run([sys.executable, SCRIPT, tmp_path], check=True, capture_output=True)
    page = (tmp_path / "index.html").read_text()
    assert '<a href="bw2calc/index.html">bw2calc</a><p>One score,' in page
    assert "&lt;odd&gt;/index.html" in page  # folder names are escaped
    assert "empty/" not in page
