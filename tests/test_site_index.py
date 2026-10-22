"""scripts/site_index.py on a site folder with one asv subject and one stray folder."""

import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "site_index.py"
NAV = '<li id="nav-li-" class="active"><a href="#/">Benchmark grid</a></li>'  # asv's menu, first tab


def test_links_each_built_subject_with_its_description(tmp_path: Path):
    (tmp_path / "bw2calc").mkdir()
    (tmp_path / "bw2calc" / "index.html").write_text(NAV)
    (tmp_path / "<odd>").mkdir()
    (tmp_path / "<odd>" / "index.html").write_text(NAV)
    (tmp_path / "empty").mkdir()  # no index.html: not a built subject
    subprocess.run([sys.executable, SCRIPT, tmp_path], check=True, capture_output=True)
    page = (tmp_path / "index.html").read_text()
    assert '<a href="bw2calc/index.html">bw2calc</a><p>One score,' in page
    assert "%3Codd%3E/index.html" in page  # folder names are URL-encoded in the link
    assert ">&lt;odd&gt;</a>" in page  # and HTML-escaped in the text
    assert "empty/" not in page


def test_links_each_subject_back_once(tmp_path: Path):
    (tmp_path / "bw2calc").mkdir()
    (tmp_path / "bw2calc" / "index.html").write_text(NAV)
    for _ in range(2):  # a rebuild of the index must not add a second tab
        subprocess.run([sys.executable, SCRIPT, tmp_path], check=True, capture_output=True)
    back = '<li><a href="../index.html">All benchmarks</a></li>'
    assert (tmp_path / "bw2calc" / "index.html").read_text() == back + NAV


def test_refuses_a_subject_page_without_asvs_menu(tmp_path: Path):
    (tmp_path / "bw2calc").mkdir()
    (tmp_path / "bw2calc" / "index.html").write_text("<html></html>")
    run = subprocess.run([sys.executable, SCRIPT, tmp_path], capture_output=True, text=True, check=False)
    assert run.returncode != 0
    assert "no asv navbar" in run.stderr


def test_start_link_points_at_a_real_benchmark():
    # The front page links bw2calc's "time for one score" graph by its asv name.
    bench = (SCRIPT.parents[1] / "benchmarks" / "bench_bw2calc" / "bench_lca.py").read_text()
    assert "#bench_lca.SingleScore.time_first_score" in SCRIPT.read_text()
    # The asv adapter names the method time_<function name> (src/bwbench/asv.py).
    assert 'asv="SingleScore"' in bench.split("def first_score(")[0].rsplit("@bench", 1)[1]
