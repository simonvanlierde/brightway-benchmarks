#!/usr/bin/env python3
"""Write site/index.html linking each subject's asv site, and link each asv site back to it.

Usage: site_index.py SITE_DIR.
"""

import html
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
(site / "index.html").write_text(f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Brightway benchmarks</title>
<meta name="description" content="How long Brightway's LCA calculations take in each released version,
on synthetic ecoinvent-sized databases.">
<style>
:root {{ color-scheme: light dark; --fg: #1d1d1f; --bg: #fff; --muted: #5f6368; --line: #dadce0; --link: #0b57d0; }}
@media (prefers-color-scheme: dark) {{
  :root {{ --fg: #e8eaed; --bg: #16171a; --muted: #9aa0a6; --line: #3c4043; --link: #8ab4f8; }}
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

<h2>Reading the graphs</h2>
<ul>
<li>Each point is one release. Lower is faster.</li>
<li>Each line is one environment. For bw2calc the environment name says the solver:
<code>pypardiso</code>, <code>scikit-umfpack</code>, or neither for SciPy's SuperLU.</li>
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
