#!/usr/bin/env python3
"""asv results as the UI's data: ``export_ui.py RESULTS_DIR OUT_DIR``.

Reads RESULTS_DIR (a checkout of the ``results`` branch) and writes OUT_DIR/index.json and one
report per commit, subject and machine under OUT_DIR/reports/, in the shapes ui/schema/
describes. Each subject is a group, each machine folder a machine of its own, so results from
two machines are never pooled.

A case is one benchmark at one parameter set in one environment. The environment drops its
stack hash (scripts/asv.sh), so a case keeps its id across releases. Where a commit ran in one
environment on several stacks, the current stack (the hash of asv/SUBJECT.stack.txt) wins, else
the lowest hash, as in scripts/release_changes.py. A benchmark's measure comes from its asv
``type`` in benchmarks.json: ``time`` is latency in nanoseconds, with asv's 99% interval as the
bounds where it holds the value, and ``peakmemory`` peak memory in bytes. Other types, such as
``track``, are left out, as are failed and skipped cases. A benchmark whose results have more or
fewer parameters than benchmarks.json names is skipped, with one warning.

Release tags come from asv/SUBJECT.hashes and resolve through asv's mirror of the upstream
repository, .asv/SUBJECT. asv/ and .asv/ are read from the working directory.
"""

import ast
import hashlib
import itertools
import json
import math
import re
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from release_changes import SHA, STACK, current_stack, pick, releases

REPO = "https://github.com/simonvanlierde/brightway-benchmarks"
PROJECT = {
    "name": "brightway-benchmarks",
    "description": "Continuous benchmarks for the Brightway LCA stack on seeded synthetic matrices",
    "url": REPO,
    "links": [{"name": "Method", "url": f"{REPO}/blob/main/docs/method.md"}],
}
MEASURES = {  # asv type -> (measure id, scale to the unit)
    "time": ("latency", 1e9),
    "peakmemory": ("peak-memory", 1),
}
MEASURE_INFO = [  # asv reports a time's median over its samples, and a peak memory's highest resident size
    {"id": "latency", "name": "Time", "unit": "ns", "better": "lower", "statistic": "median"},
    {"id": "peak-memory", "name": "Peak memory", "unit": "B", "better": "lower", "statistic": "max"},
]
REPORT_FORMAT = "bmf/v0"


def slug(name: str) -> str:
    """A stable id unique to NAME, at most 64 characters: its words, then a hash of all of it."""
    words = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:51].rstrip("-")
    return f"{words or 'x'}-{hashlib.sha256(name.encode()).hexdigest()[:12]}"


def runs(folder: Path) -> dict[tuple[str, str], list[dict]]:
    """(machine, commit) -> one result file per environment, on the stack that wins."""
    current = current_stack(folder.name)
    # (machine, commit) -> environment without its stack -> stack -> result
    found: dict[tuple[str, str], dict[str, dict[str, dict]]] = {}
    for path in folder.glob("*/*-*.json"):
        data = json.loads(path.read_text())
        stack = STACK.search(data["env_name"])
        env = found.setdefault((path.parent.name, data["commit_hash"]), {}).setdefault(
            STACK.sub("", data["env_name"]), {}
        )
        env[stack.group(1) if stack else ""] = data
    return {key: [stacks[pick(stacks, current)] for _, stacks in sorted(envs.items())] for key, envs in found.items()}


def metrics(data: dict, kinds: dict[str, str]) -> list[tuple[str, tuple[str, ...], str, dict]]:
    """(case, parameter values, measure, BMF metric) for each value in one asv result file."""
    out = []
    columns = data.get("result_columns", ["result", "params"])
    for name, row in data["results"].items():
        if kinds.get(name) not in MEASURES:
            continue
        measure, scale = MEASURES[kinds[name]]
        cell = dict(zip(columns, row, strict=False))
        params = cell.get("params") or []
        sets = list(itertools.product(*params)) if params else [()]
        values = cell["result"] if isinstance(cell["result"], list) else [cell["result"]]
        lower, upper = cell.get("stats_ci_99_a"), cell.get("stats_ci_99_b")
        for i, (point, value) in enumerate(zip(sets, values, strict=False)):
            if value is None or math.isnan(value):
                continue
            metric = {"value": value * scale}
            a, b = (lower[i], upper[i]) if lower and upper else (None, None)
            if a is not None and b is not None and math.isfinite(a) and math.isfinite(b) and a <= value <= b:
                metric |= {"lower_value": a * scale, "upper_value": b * scale}
            out.append((name, point, measure, metric))
    return out


def iso(ms: int) -> str:
    """The time asv records, in milliseconds since the epoch, as an ISO 8601 time in UTC."""
    return datetime.fromtimestamp(ms / 1000, UTC).isoformat().replace("+00:00", "Z")


def write(path: Path, data: dict) -> None:
    """DATA as compact JSON; NaN is not JSON, so it fails here rather than in the browser."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, separators=(",", ":"), allow_nan=False))


@dataclass
class Catalog:
    """The environments, benchmarks and cases seen so far, each keyed by what names it."""

    envs: dict[tuple[str, str], dict] = field(default_factory=dict)
    benchmarks: dict[tuple[str, str], dict] = field(default_factory=dict)
    cases: dict[str, dict] = field(default_factory=dict)
    skipped: set[tuple[str, str]] = field(default_factory=set)  # (subject, benchmark) already warned about

    def report(self, subject: str, files: list[dict], info: dict[str, dict]) -> dict[str, dict]:
        """One BMF report from the result files of one commit on one machine, one stack each."""
        group, kinds = slug(subject), {k: v.get("type", "") for k, v in info.items()}
        report: dict[str, dict] = {}
        for data in files:
            env = STACK.sub("", data["env_name"])
            env_id = slug(f"{subject}/{env}")
            for name, point, measure, metric in metrics(data, kinds):
                names = info[name].get("param_names", [])
                if len(point) != len(names):  # the values would land on the wrong axes
                    if (subject, name) not in self.skipped:
                        self.skipped.add((subject, name))
                        print(
                            f"export_ui: {subject} {name} has {len(point)} parameters where benchmarks.json"
                            f" names {len(names)}; skipped",
                            file=sys.stderr,
                        )
                    continue
                axes = [{"name": n, "values": []} for n in names]
                bench = self.benchmarks.setdefault(
                    (subject, name),
                    {
                        "id": slug(f"{subject}/{name}"),
                        "group": group,
                        "name": name,
                        "measures": [measure],
                        "params": axes,
                    },
                )
                for axis, value in zip(bench["params"], point, strict=True):
                    if value not in axis["values"]:
                        axis["values"].append(value)
                self.envs.setdefault((subject, env), {"id": env_id, "group": group, "name": env})
                key = json.dumps([subject, name, list(point), env])  # unambiguous, whatever the values hold
                case = self.cases.setdefault(
                    key, {"id": slug(key), "benchmark": bench["id"], "environment": env_id, "params": list(point)}
                )
                if case["id"] in report:  # two stacks of one environment: one would overwrite the other
                    sys.exit(f"export_ui: {key} twice in one report")
                report[case["id"]] = {measure: metric}
        return report

    def order(self, subject: str, info: dict[str, dict]) -> None:
        """Sort SUBJECT's axis values as benchmarks.json lists them, the rest as they came, and label them."""
        for (s, name), bench in self.benchmarks.items():
            if s != subject:
                continue
            listed = info[name].get("params", [])
            for i, axis in enumerate(bench["params"]):
                known = listed[i] if i < len(listed) else []
                axis["values"].sort(key=lambda v, known=known: known.index(v) if v in known else len(known))
                axis["labels"] = [label(v) for v in axis["values"]]


def label(value: str) -> str:
    """A parameter value as asv writes it (Python's repr), shown plainly: 'LCA' as LCA."""
    try:
        return str(ast.literal_eval(value))
    except (ValueError, SyntaxError, TypeError, MemoryError, RecursionError):
        return value


def export(results: Path, out: Path) -> dict:
    """Write OUT/index.json and OUT/reports/ from RESULTS, and return the index."""
    groups, commits, reports = [], [], []
    machines: dict[str, dict] = {}
    catalog = Catalog()
    for meta in sorted(results.glob("*/benchmarks.json")):
        subject = meta.parent.name
        group = slug(subject)
        conf_file = Path(f"asv/{subject}.json")
        conf = json.loads(conf_file.read_text()) if conf_file.exists() else {}
        groups.append({"id": group, "name": subject} | ({"url": conf["project_url"]} if "project_url" in conf else {}))
        info = {k: v for k, v in json.loads(meta.read_text()).items() if isinstance(v, dict)}  # skips "version"
        dates: dict[str, int] = {}
        for (machine, commit), files in sorted(runs(meta.parent).items()):
            report = catalog.report(subject, files, info)
            if not report:
                continue
            machine_id = machines.setdefault(machine, {"id": slug(machine), "name": machine})["id"]
            dates[commit] = max(dates.get(commit, 0), *(f["date"] for f in files))
            path = f"reports/{group}/{machine_id}/{commit}.json"
            write(out / path, report)
            reports.append(
                {"path": path, "format": REPORT_FORMAT, "group": group, "machine": machine_id, "commit": commit}
            )
        catalog.order(subject, info)
        tags = {c: t[:8] if SHA.fullmatch(t) else t for c, t in releases(subject, "export_ui").items()}
        for commit, date in sorted(dates.items(), key=lambda c: (c[1], c[0])):
            tag = tags.get(commit[:8])
            commits.append({"id": commit, "group": group, "date": iso(date)} | ({"release": tag} if tag else {}))
    index = {
        "format_version": 1,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "project": PROJECT,
        "groups": groups,
        "measures": MEASURE_INFO,
        "machines": list(machines.values()),
        "environments": list(catalog.envs.values()),
        "benchmarks": list(catalog.benchmarks.values()),
        "cases": list(catalog.cases.values()),
        "commits": commits,
        "reports": reports,
    }
    write(out / "index.json", index)
    return index


if __name__ == "__main__":
    index = export(Path(sys.argv[1]), Path(sys.argv[2]))
    counts = ", ".join(f"{len(index[k])} {k}" for k in ("groups", "benchmarks", "cases", "commits", "reports"))
    print(f"export_ui: {counts}", file=sys.stderr)
