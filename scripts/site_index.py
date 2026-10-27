#!/usr/bin/env python3
"""Write site/index.html linking each subject's asv site, and link each asv site back to it.

With SITE_DIR/compat/status.json (from compat_site.py) the page also gets the "Works together
today" table: each compat job's state in the latest run and its last green set.

Usage: site_index.py SITE_DIR.
"""

import html
import json
import sys
import urllib.parse
from datetime import UTC, datetime
from pathlib import Path

REPO = "https://github.com/simonvanlierde/brightway-benchmarks"
# What each history times, in LCA terms; the README's "What is measured" table says the same.
ABOUT = {
    "bw2calc": "One score, a second functional unit, many functional units at once, and Monte Carlo"
    " draws, with each direct solver (SuperLU, PyPardiso, UMFPACK) and the iterative ones.",
    "bw2data": "Writing a database, up to the size of ecoinvent.",
    "bw_graph_tools": "Supply-chain graph traversal, small and large.",
    "bw_processing": "Building datapackages from many resource groups.",
    "bw_timex": "The time-explicit LCI as the timeline grows.",
    "matrix_utils": "Building matrices from many resource groups.",
}

site = Path(sys.argv[1])
subjects = sorted(p.name for p in site.iterdir() if (p / "index.html").exists())
# asv's navbar has no link out of a subject's site, so add one as its first tab.
NAV = '<li id="nav-li-" class="active">'
BACK = '<li><a href="../index.html">All benchmarks</a></li>'
for s in subjects:
    page = site / s / "index.html"
    text = page.read_text()
    if BACK not in text:
        if NAV not in text:
            msg = f"{page}: no asv navbar to add the back link to"
            raise SystemExit(msg)
        page.write_text(text.replace(NAV, BACK + NAV, 1))
items = "\n".join(
    f'<li><a href="{html.escape(urllib.parse.quote(s))}/index.html">{html.escape(s)}</a>'
    f"<p>{html.escape(ABOUT.get(s, ''))}</p></li>"
    for s in subjects
)


def compat_section(status_file: Path) -> str:
    """The compat table's HTML, or nothing before compat_site.py has run."""
    status = json.loads(status_file.read_text()) if status_file.exists() else {"cells": []}
    if not status["cells"]:
        return ""
    e = html.escape
    rows = []
    for c in status["cells"]:
        g = c["green"]
        if g:
            v = g["versions"]
            files = " · ".join(f'<a href="{e(g["dir"])}/{f}">{f}</a>' for f in ("requirements.txt", "pylock.toml"))
            last = f'<a href="{e(g["run"])}">{e(g["date"])}</a>'
            pins = "".join(
                f"<td>{e(v.get(p, '-'))}</td>" for p in ("brightway25", "bw2calc", "bw2data", "bw2io", "numpy")
            )
        else:
            files, last, pins = "", "none kept", '<td colspan="5"></td>'
        ok = c["today"] == "success"
        rows.append(
            f"<tr><td>{e(c['python'])}</td><td>{e(c['os'])}</td><td>{e(c['column'])}</td>"
            f'<td class="{"ok" if ok else "bad"}">{"green" if ok else e(c["today"] or "unknown")}</td>'
            f"<td>{last}</td>{pins}<td>{files}</td></tr>"
        )
    return f"""
<h2 id="works-together">Works together today</h2>
<p>Each night the <code>compat</code> workflow installs the newest Brightway releases from PyPI
on each Python and runs every case once on a small database (<code>latest</code>), and again with
Brightway's dependencies at their lowest allowed versions (<code>floors</code>) or with
pre-releases (<code>pre</code>). The table shows how each job ended in the
<a href="{e(status["run"])}">run of {e(status["date"])}</a>, and the last set that passed. Its
<code>requirements.txt</code> works as a constraints file, as in
<code>uv pip install brightway25 -c requirements.txt</code>; <code>pylock.toml</code> pins
the same set with each wheel's hash for that operating system. Both include pytest, which the
run needs. A set is kept for 90 days.</p>
<div class="wide"><table class="compat">
<thead><tr><th>Python</th><th>OS</th><th>Column</th><th>Latest run</th><th>Last green</th><th>brightway25</th>
<th>bw2calc</th><th>bw2data</th><th>bw2io</th><th>numpy</th><th>Files</th></tr></thead>
<tbody>
{"\n".join(rows)}
</tbody>
</table></div>
"""


(site / "index.html").write_text(f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Brightway benchmarks</title>
<meta name="description" content="How long Brightway's LCA calculations take in each released version,
on synthetic ecoinvent-sized databases.">
<style>
:root {{ color-scheme: light dark; --fg: #1d1d1f; --bg: #fff; --muted: #5f6368; --line: #dadce0; --link: #0b57d0;
  --ok: #137333; --bad: #b3261e; }}
@media (prefers-color-scheme: dark) {{
  :root {{ --fg: #e8eaed; --bg: #16171a; --muted: #9aa0a6; --line: #3c4043; --link: #8ab4f8;
    --ok: #81c995; --bad: #f28b82; }}
}}
body {{ font: 1rem/1.55 system-ui, sans-serif; color: var(--fg); background: var(--bg);
  max-width: 44rem; margin: 0 auto; padding: 2.5rem 1rem; }}
h1 {{ font-size: 1.8rem; margin: 0 0 .5rem; }}
h2 {{ font-size: 1.1rem; margin: 2rem 0 .5rem; }}
a {{ color: var(--link); }}
.lead {{ color: var(--muted); margin: 0; }}
ul.subjects {{ list-style: none; padding: 0; margin: 0; }}
ul.subjects li {{ border-top: 1px solid var(--line); padding: .75rem 0; }}
ul.subjects li:last-child {{ border-bottom: 1px solid var(--line); }}
ul.subjects a {{ display: inline-block; padding: .25rem 0; font-weight: 600; font-family: ui-monospace, monospace; }}
ul.subjects p {{ margin: .2rem 0 0; color: var(--muted); }}
.wide {{ overflow-x: auto; }}
table.compat {{ border-collapse: collapse; font-size: .85rem; white-space: nowrap; }}
table.compat th, table.compat td {{ border-bottom: 1px solid var(--line); padding: .3rem .5rem; text-align: left; }}
table.compat .ok {{ color: var(--ok); }}
table.compat .bad {{ color: var(--bad); font-weight: 600; }}
footer {{ margin-top: 2.5rem; color: var(--muted); font-size: .9rem; }}
</style>
</head>
<body>
<main>
<h1>Brightway benchmarks</h1>
<p class="lead">How long Brightway's calculations take in each released version, and whether
they still give the right score. Every case runs on a synthetic database with the structure
of ecoinvent, so no licensed data is involved.</p>

<p>Start with <a href="bw2calc/index.html#bench_lca.SingleScore.time_first_score">bw2calc's
time for one score</a> on the ecoinvent-sized database, per solver, across every release since 2.0.
What the histories show so far is in the <a href="{REPO}#results-so-far">README</a>.</p>

<h2>Histories</h2>
<ul class="subjects">
{items}
</ul>
{compat_section(site / "compat" / "status.json")}
<h2>Reading the graphs</h2>
<ul>
<li>Each point is one release. Lower is faster.</li>
<li>Each line is one environment. For bw2calc the environment name says the solver:
<code>pypardiso</code>, <code>scikit-umfpack</code>, or neither for SciPy's SuperLU. A name with
<code>BWBENCH_SOLVER</code> is an experimental solver patched into bw2calc: <code>klu</code>
(KLU, through pyklu) or <code>umfpack-T</code> (UMFPACK factorizing Aᵀ).</li>
<li>Only the package changes along a line. Its dependencies stay fixed, so a step is the
package's own change.</li>
<li>Every timing ran one thread, pinned to one set of CPU cores. Compare points within a
line, not times between machines.</li>
</ul>
</main>
<footer>Code, method and caveats: <a href="{REPO}">{REPO.removeprefix("https://")}</a>.
Built {datetime.now(UTC):%Y-%m-%d}.</footer>
</body>
</html>
""")
print(f"{site / 'index.html'}: {len(subjects)} subjects")
