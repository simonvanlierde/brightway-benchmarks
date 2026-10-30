#!/usr/bin/env python3
"""What moved in the latest release: ``release_changes.py SUBJECT RESULTS_DIR``.

For each environment in RESULTS_DIR/SUBJECT, compares the newest two releases in
asv/SUBJECT.hashes that have results there, and prints the cases whose value moved by more
than ``THRESHOLD``, as a Markdown table. A case that failed (asv's null) on one side and ran
on the other is listed too, and so is one that ran before and is skipped now; one skipped
before and running now is new, not a change, so it is left out. ``track_`` cases count errors or
steps, not time or memory, so they are left out.

An environment's name ends in the hash of its fixed dependency stack (scripts/asv.sh). The
comparison prefers two results on the same stack, the current one (asv/SUBJECT.stack.txt)
first; when there are none, it compares across stacks and flags the row, because then the
dependencies moved too, not only the package.
Release tags resolve through asv's mirror of the upstream repository, .asv/SUBJECT, which
``asv run`` and ``asv publish`` create.
"""

import hashlib
import itertools
import json
import math
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from release_report import sha

HEADER = ("environment", "releases", "case", "parameters", "old", "new", "new / old")
THRESHOLD = 0.05  # pinned run-to-run noise is 0.4 to 1.5% (just noise)
GB = 1e9
STACK = re.compile(r"-BWBENCH_STACK([0-9a-f]+)")
SHA = re.compile(r"[0-9a-f]{40}")


@dataclass(frozen=True)
class Change:
    """One case at one parameter set whose value moved between two releases."""

    env: str  # machine/environment, without the stack hash
    old_tag: str
    new_tag: str
    stack_moved: bool  # the two results ran on different dependency stacks
    case: str
    params: str
    old: str  # the value with its unit, or "failed" or "skipped"
    new: str
    ratio: float | None  # new / old; None when one side has no value

    def cells(self) -> tuple[str, ...]:
        """The row as text, one cell per HEADER column."""
        moved = " (stack moved)" if self.stack_moved else ""
        ratio = "" if self.ratio is None else f"{self.ratio:.2f}"
        releases = f"{self.old_tag} → {self.new_tag}{moved}"
        return (self.env, releases, self.case, self.params, self.old, self.new, ratio)


def show(value: float | None, unit: str) -> str:
    """A value as the table shows it."""
    if value is None:
        return "failed"
    if math.isnan(value):
        return "skipped"
    if unit == "bytes":
        return f"{value / GB:.3g} GB" if value >= GB else f"{value / 1e6:.3g} MB"
    text = f"{value:.3g}" if value < 1000 else f"{value:.0f}"  # 1234 s, not 1.23e+03 s
    return f"{text} s" if unit == "seconds" else text


def changes(results: Path, subject: str, threshold: float = THRESHOLD) -> list[Change]:
    """The cases that moved more than THRESHOLD in each environment's newest release."""
    folder = results / subject
    tags = Path(f"asv/{subject}.hashes").read_text().split()
    order = {sha(Path(".asv") / subject, t): t for t in tags}
    # sha() falls back to the tag itself; a commit listed by its full hash needs no mirror
    unresolved = [t for c, t in order.items() if c == t[:8] and not SHA.fullmatch(t)]
    if unresolved:  # a missing or stale mirror would otherwise compare older releases unannounced
        missing = ", ".join(unresolved)
        print(f"release_changes: .asv/{subject} lacks {missing}; `just bench {subject}` refreshes it", file=sys.stderr)
    stack_file = Path(f"asv/{subject}.stack.txt")
    current = hashlib.sha256(stack_file.read_bytes()).hexdigest()[:8] if stack_file.exists() else ""
    meta = folder / "benchmarks.json"
    cases = json.loads(meta.read_text()) if meta.exists() else {}
    units = {k: v.get("unit", "") for k, v in cases.items() if isinstance(v, dict)}  # skips "version"
    # (machine, environment) -> tag -> stack -> results
    runs: dict[tuple[str, str], dict[str, dict[str, dict]]] = {}
    for path in folder.glob("*/*-*.json"):
        data = json.loads(path.read_text())
        tag = order.get(data.get("commit_hash", "")[:8])
        if tag is None:  # a commit between releases, from a range run
            continue
        env = data.get("env_name", "")
        stack = STACK.search(env)
        key = (path.parent.name, STACK.sub("", env))
        runs.setdefault(key, {}).setdefault(tag, {})[stack.group(1) if stack else ""] = data
    out = []
    for (machine, env), by_tag in sorted(runs.items()):
        if len(by_tag) < 2:
            continue
        old_tag, new_tag = sorted(by_tag, key=tags.index)[-2:]
        old, new = by_tag[old_tag], by_tag[new_tag]
        shared = old.keys() & new.keys()
        pick = lambda stacks: min(stacks, key=lambda s: (s != current, s))  # noqa: E731
        old_stack, new_stack = (pick(shared), pick(shared)) if shared else (pick(old), pick(new))
        rows = compare(old[old_stack], new[new_stack], units, threshold)
        out.extend(Change(f"{machine}/{env}", old_tag, new_tag, not shared, *row) for row in rows)
    return out


def compare(old: dict, new: dict, units: dict, threshold: float) -> list[tuple]:
    """(case, params, old, new, ratio) for each parameter set of each case that moved."""
    rows = []
    for name in sorted(old["results"].keys() & new["results"].keys()):
        if name.rsplit(".", 1)[-1].startswith("track_"):
            continue
        a, b = old["results"][name], new["results"][name]
        params = a[1] if len(a) > 1 and a[1] else []
        labels = [", ".join(p) for p in itertools.product(*params)] if params else [""]
        before = a[0] if isinstance(a[0], list) else [a[0]]
        after = b[0] if isinstance(b[0], list) else [b[0]]
        if b[1:2] != a[1:2]:  # the parameters changed, so the values do not line up
            continue
        for label, x, y in zip(labels, before, after, strict=False):
            ran_x, ran_y = x is not None and not math.isnan(x), y is not None and not math.isnan(y)
            if not ran_x and not ran_y:
                continue
            if x is not None and math.isnan(x):  # skipped in the older release: a new case, not a change
                continue
            ratio = y / x if ran_x and ran_y and x else None
            if ratio is not None and abs(ratio - 1) <= threshold:
                continue
            unit = units.get(name, "")
            rows.append((name.split(".", 1)[1], label, show(x, unit), show(y, unit), ratio))
    return rows


def markdown(rows: list[Change]) -> str:
    """The changes as a Markdown table."""
    lines = [HEADER, ("---",) * len(HEADER), *(c.cells() for c in rows)]
    return "\n".join(f"| {' | '.join(cells)} |" for cells in lines)


if __name__ == "__main__":
    print(markdown(changes(Path(sys.argv[2]), sys.argv[1])))
