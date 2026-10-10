#!/usr/bin/env python3
"""Write site/index.html linking each subject's asv site. Usage: site_index.py SITE_DIR."""

import html
import sys
from pathlib import Path

site = Path(sys.argv[1])
subjects = sorted(p.name for p in site.iterdir() if (p / "index.html").exists())
items = "\n".join(f'<li><a href="{html.escape(s)}/index.html">{html.escape(s)}</a></li>' for s in subjects)
(site / "index.html").write_text(f"""<!doctype html>
<html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Brightway benchmarks</title>
<body style="font-family: system-ui, sans-serif; max-width: 40rem; margin: 2rem auto; padding: 0 1rem">
<h1>Brightway benchmarks</h1>
<p>Timings across released versions on seeded synthetic systems. Each subject has its own history.</p>
<ul>
{items}
</ul>
</body></html>
""")
print(f"{site / 'index.html'}: {len(subjects)} subjects")
