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
bounds, and ``peakmemory`` peak memory in bytes. Other types, such as ``track``, are left out, as
are failed and skipped cases.

Release tags come from asv/SUBJECT.hashes and resolve through asv's mirror of the upstream
repository, .asv/SUBJECT. asv/ and .asv/ are read from the working directory.
"""

import hashlib
import itertools
import json
import math
import re
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from release_changes import SHA, STACK
from release_report import sha

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
MEASURE_INFO = [
    {"id": "latency", "name": "Time", "unit": "ns"},
    {"id": "peak-memory", "name": "Peak memory", "unit": "B"},
]
REPORT_FORMAT = "bmf/v0"


def slug(name: str) -> str:
    """A stable id unique to NAME, at most 64 characters: its words, then a hash of all of it."""
    words = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:51].rstrip("-")
    return f"{words}-{hashlib.sha256(name.encode()).hexdigest()[:12]}"


def runs(folder: Path) -> dict[tuple[str, str], list[dict]]:
    """(machine, commit) -> one result file per environment, on the stack that wins."""
    stack_file = Path(f"asv/{folder.name}.stack.txt")
    current = hashlib.sha256(stack_file.read_bytes()).hexdigest()[:8] if stack_file.exists() else ""
    # (machine, commit) -> environment without its stack -> stack -> result
    found: dict[tuple[str, str], dict[str, dict[str, dict]]] = {}
    for path in folder.glob("*/*-*.json"):
        data = json.loads(path.read_text())
        stack = STACK.search(data["env_name"])
        env = found.setdefault((path.parent.name, data["commit_hash"]), {}).setdefault(
            STACK.sub("", data["env_name"]), {}
        )
        env[stack.group(1) if stack else ""] = data
    return {
        key: [stacks[min(stacks, key=lambda s: (s != current, s))] for _, stacks in sorted(envs.items())]
        for key, envs in found.items()
    }


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
            if a is not None and b is not None and math.isfinite(a) and math.isfinite(b):
                metric |= {"lower_value": a * scale, "upper_value": b * scale}
            out.append((name, point, measure, metric))
    return out


def releases(subject: str) -> dict[str, str]:
    """The first 8 characters of each release's commit -> its tag, from asv/SUBJECT.hashes."""
    hashes = Path(f"asv/{subject}.hashes")
    tags = hashes.read_text().split() if hashes.exists() else []
    out = {}
    for tag in tags:
        commit = sha(Path(".asv") / subject, tag)
        if commit == tag[:8] and not SHA.fullmatch(tag):  # sha() falls back to the tag itself
            print(f"export_ui: .asv/{subject} lacks {tag}; `just bench {subject}` refreshes it", file=sys.stderr)
            continue
        out[commit] = tag[:8] if SHA.fullmatch(tag) else tag
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

    def report(self, subject: str, files: list[dict], info: dict[str, dict]) -> dict[str, dict]:
        """One BMF report from the result files of one commit on one machine, one stack each."""
        group, kinds = slug(subject), {k: v.get("type", "") for k, v in info.items()}
        report: dict[str, dict] = {}
        for data in files:
            env = STACK.sub("", data["env_name"])
            env_id = slug(f"{subject}/{env}")
            for name, point, measure, metric in metrics(data, kinds):
                axes = [{"name": n, "values": []} for n in info[name].get("param_names", [])]
                bench = self.benchmarks.setdefault(
                    (subject, name),
                    {"id": slug(f"{subject}/{name}"), "group": group, "name": name, "measure": measure, "params": axes},
                )
                if len(point) != len(bench["params"]):
                    sys.exit(f"export_ui: {subject} {name} has {len(point)} parameters, benchmarks.json names others")
                for axis, value in zip(bench["params"], point, strict=True):
                    if value not in axis["values"]:
                        axis["values"].append(value)
                self.envs.setdefault((subject, env), {"id": env_id, "group": group, "name": env})
                key = f"{subject}/{name}({', '.join(point)}) [{env}]"
                case = self.cases.setdefault(
                    key, {"id": slug(key), "benchmark": bench["id"], "environment": env_id, "params": list(point)}
                )
                if case["id"] in report:  # two stacks of one environment: one would overwrite the other
                    sys.exit(f"export_ui: {key} twice in one report")
                report[case["id"]] = {measure: metric}
        return report


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
        tags = releases(subject)
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
