"""Every finding in docs/findings.md says how to rerun it (.github/CONTRIBUTING.md, "Report a finding")."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"


def recipes() -> set[str]:
    text = "\n".join(p.read_text() for p in [ROOT / "justfile", *ROOT.glob("just/*.just")])
    return set(re.findall(r"^@?([a-z][\w-]*)(?:\s[^\n:]*)?:(?!=)", text, re.MULTILINE))


def problems(text: str, known: set[str]) -> list[str]:
    """One line per `###` section that names no rerun, or names one that doesn't exist."""
    out = []
    for section in re.split(r"^(?=### )", text, flags=re.MULTILINE)[1:]:
        title = section.splitlines()[0]
        paths = re.findall(r"\]\((\.\./(?:benchmarks|scripts|src)/[^)#\s]+)", section)
        commands = re.findall(r"`just ([\w-]+)", section)
        out += [f"{title}: {p} is missing" for p in paths if not (DOCS / p).exists()]
        out += [f"{title}: no recipe `just {c}`" for c in commands if c not in known]
        if not paths and not commands:
            out.append(f"{title}: no rerun link")
    return out


def test_every_finding_links_its_rerun() -> None:
    assert problems((DOCS / "findings.md").read_text(), recipes()) == []


def test_problems_catches_missing_and_broken_reruns() -> None:
    text = "### A\nno link\n### B\n[x](../scripts/nope.py) `just nope`\n### C\n`just bench bw2calc`\n"
    assert problems(text, {"bench"}) == [
        "### A: no rerun link",
        "### B: ../scripts/nope.py is missing",
        "### B: no recipe `just nope`",
    ]
