#!/usr/bin/env python3
"""asv results as the UI's data: ``export_ui.py RESULTS_DIR OUT_DIR``.

Reads RESULTS_DIR (a checkout of the ``results`` branch), and asv/ and asv's mirrors in .asv/ from
the working directory. Writes OUT_DIR/index.json and one report per commit, subject and machine,
in the shapes ui/schema/ gives. An environment's name drops its stack hash, so a case keeps its
id across releases, and a commit gets one value per environment, on the stack ``pick`` chooses.
``time`` cases become latency in ns, with the samples' quartiles as bounds where they hold the value;
``peakmemory`` cases become peak memory in bytes. Other types, failed and skipped cases are left
out, and so is a benchmark whose parameters don't match benchmarks.json, with one warning.

The index also lists ``changes``, found here so the UI computes none. Along each series (one case
on one machine in one measure, oldest commit first) two methods run:

- ``release``: between each two releases in a row, a change counts when new / old moves by more
  than the case's noise allows (``release_changes.noise_threshold``, the rule the site's table
  uses too).
- ``change-point``: Apache Otava's change points (scripts/change_points.py, run through uv), where
  the mean level moved by more than ``NOISE_FLOOR``.
"""

import ast
import hashlib
import itertools
import json
import math
import re
import shutil
import subprocess
import sys
import tomllib
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote

from export_guidance import PUBLIC_BASE
from output_path import output_path
from release_changes import NOISE_FLOOR, SHA, STACK, current_stack, noise_threshold, pick, releases

REPO = "https://github.com/simonvanlierde/brightway-benchmarks"
CODSPEED = "https://app.codspeed.io/simonvanlierde/brightway-benchmarks"
PROJECT = {
    "name": "brightway-benchmarks",
    "description": "Continuous benchmarks for the Brightway LCA stack on seeded synthetic matrices",
    "url": REPO,
    "links": [
        {"name": "Method", "url": f"{REPO}/blob/main/docs/method.md"},
        {"name": "Cite", "url": "https://doi.org/10.5281/zenodo.23727602"},
    ],
}
MEASURES = {  # asv type -> (measure id, scale to the unit)
    "time": ("latency", 1e9),
    "peakmemory": ("peak-memory", 1),
}
MEASURE_INFO = [  # asv gives a time's median and a peak memory's highest resident size
    {
        "id": "latency",
        "name": "Time",
        "unit": "ns",
        "better": "lower",
        "statistic": "median",
        "bounds": "the middle half of the samples",
    },
    {"id": "peak-memory", "name": "Peak memory", "unit": "B", "better": "lower", "statistic": "max"},
]
REPORT_FORMAT = "bmf/v0"
CHANGE_POINTS = Path(__file__).with_name("change_points.py")
DESCRIPTIONS = Path(__file__).resolve().parents[1] / "benchmarks" / "descriptions.toml"
FINDINGS = DESCRIPTIONS.with_name("findings.toml")
PROFILES = DESCRIPTIONS.parents[1] / "profiles"  # `just site` publishes this folder at PUBLIC_BASE/profiles/


def slug(name: str) -> str:
    """A stable id unique to NAME, at most 64 characters: its words, then a hash of all of it."""
    words = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:51].rstrip("-")
    return f"{words or 'x'}-{hashlib.sha256(name.encode()).hexdigest()[:12]}"


def runs(folder: Path) -> dict[tuple[str, str], list[dict]]:
    """(machine, commit) -> one result file per environment, on the stack that wins."""
    current = current_stack(folder.name)
    found: dict[tuple[str, str], dict[str, dict[str, dict]]] = {}
    for path in folder.glob("*/*-*.json"):
        data = json.loads(path.read_text())
        if not SHA.fullmatch(data["commit_hash"]):  # it becomes part of a report's path
            sys.exit(f"export_ui: {path}: commit_hash is not a full hash")
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
        # The quartiles, not asv's 99% interval: from a handful of samples that interval runs
        # to below zero and says nothing.
        q25, q75 = cell.get("stats_q_25"), cell.get("stats_q_75")
        for i, (point, value) in enumerate(zip(sets, values, strict=False)):
            if value is None or math.isnan(value):
                continue
            metric = {"value": value * scale}
            a, b = (q25[i], q75[i]) if q25 and q75 and i < min(len(q25), len(q75)) else (None, None)
            if a is not None and b is not None and math.isfinite(a) and math.isfinite(b) and 0 <= a <= value <= b:
                metric |= {"lower_value": a * scale, "upper_value": b * scale}
            out.append((name, point, measure, metric))
    return out


def spread(metric: dict) -> float | None:
    """The middle half of the samples over the value, where the metric has its quartiles."""
    if "lower_value" not in metric or metric["value"] <= 0:
        return None
    return (metric["upper_value"] - metric["lower_value"]) / metric["value"]


def iso(ms: int) -> str:
    """The time asv records, in milliseconds since the epoch, as an ISO 8601 time in UTC."""
    return datetime.fromtimestamp(ms / 1000, UTC).isoformat().replace("+00:00", "Z")


def write(path: Path, data: dict) -> None:
    """DATA as compact JSON; NaN is not JSON, so it fails here rather than in the browser."""
    output_path(path).parent.mkdir(parents=True, exist_ok=True)
    output_path(path).write_text(
        json.dumps(data, separators=(",", ":"), allow_nan=False) + "\n"
    )  # a final newline, as the end-of-file hook wants


@dataclass
class Catalog:
    """The environments, benchmarks and cases seen so far, each keyed by what names it."""

    envs: dict[tuple[str, str], dict] = field(default_factory=dict)
    benchmarks: dict[tuple[str, str], dict] = field(default_factory=dict)
    cases: dict[str, dict] = field(default_factory=dict)
    warned: set[tuple[str, str]] = field(default_factory=set)

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
                    if (subject, name) not in self.warned:
                        self.warned.add((subject, name))
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


# bw2calc's sparse solver in an environment, by what its name pins: BWBENCH_SOLVER first, since
# umfpack-T installs the same packages as umfpack. Without any of them, scipy's SuperLU solves.
SOLVERS = [
    (re.compile(r"BWBENCH_SOLVERumfpack-T"), "UMFPACK on Aᵀ"),
    (re.compile(r"BWBENCH_SOLVERklu|pyklu"), "KLU"),
    (re.compile(r"pypardiso"), "PyPardiso"),
    (re.compile(r"scikit-umfpack"), "UMFPACK"),
]
BLAS = [(re.compile(r"(^|-)(libblas_=__)?mkl"), "MKL"), (re.compile(r"openblas"), "OpenBLAS")]


def solver_labels(names: list[str]) -> list[str] | None:
    """A solver name for each environment in NAMES, with its BLAS where the name pins one.

    None when no name pins a solver, so the labels would tell nothing apart. Labels that clash
    are fine here: the UI then shows the full names.
    """
    if not any(rx.search(n) for n in names for rx, _ in SOLVERS):
        return None
    labels = []
    for n in names:
        solver = next((text for rx, text in SOLVERS if rx.search(n)), "SuperLU")
        blas = next((text for rx, text in BLAS if rx.search(n)), None)
        labels.append(f"{solver}, {blas}" if blas else solver)
    return labels


def label(value: str) -> str:
    """A parameter value as asv writes it (Python's repr), shown plainly: 'LCA' as LCA."""
    try:
        return str(ast.literal_eval(value))
    except (ValueError, SyntaxError, TypeError, MemoryError, RecursionError):
        return value


def describe(benchmarks: list[dict], about: dict) -> None:
    """Add ABOUT's text and links (descriptions.toml) to each benchmark, its parameters and values.

    Value notes and links line up with the parameter's values, an empty string where there is none.
    """
    for bench in benchmarks:
        if text := about.get("benchmarks", {}).get(bench["name"]):
            bench["description"] = text
        else:
            print(f"export_ui: {bench['name']} has no entry in {DESCRIPTIONS.name}", file=sys.stderr)
        for axis in bench["params"]:
            if text := about.get("params", {}).get(axis["name"]):
                axis["description"] = text
            known = about.get("values", {}).get(axis["name"], {})
            notes = [known.get(shown, "") for shown in axis.get("labels", axis["values"])]
            if any(notes):
                axis["notes"] = notes
            known = about.get("links", {}).get("values", {}).get(axis["name"], {})
            links = [known.get(shown, "") for shown in axis.get("labels", axis["values"])]
            if any(links):
                axis["links"] = links


GROUP_LINKS = [
    ("source", "Source"),
    ("changelog", "Changelog"),
    ("issues", "Issues and pull requests from these benchmarks"),
]


def codspeed_tests(subject: str, root: Path) -> dict[str, set[str]]:
    """The modules benchmarks/codspeed/test_SUBJECT.py re-exports, each with its function names.

    Read from the source, not imported: the benchmarks' packages are only in the box.
    """
    entry = root / "benchmarks" / "codspeed" / f"test_{subject}.py"
    if not entry.is_file():
        return {}
    found = {}
    for node in ast.parse(entry.read_text()).body:
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("bench_"):
            module = root / "benchmarks" / f"{node.module.replace('.', '/')}.py"
            if module.is_file():
                found[node.module.rsplit(".", 1)[-1]] = {
                    f.name for f in ast.walk(ast.parse(module.read_text())) if isinstance(f, ast.FunctionDef)
                }
    return found


def codspeed_url(bench: dict, subject: str, tests: dict[str, set[str]], codspeed: dict) -> str | None:
    """CodSpeed's page for one case of a benchmark, named as bwbench.pytest names the test.

    asv's time_X and peakmem_X come from the setup function X, which pytest runs as test_X[values
    joined by -], the last axis first. A track_ method has no test, nor does a benchmark in
    CODSPEED's ``skip``. CodSpeed runs one size, so CODSPEED's ``params`` gives an axis its value
    there; an axis not in it takes its first value.
    """
    module, *_, method = bench["name"].split(".")
    kind, _, func = method.partition("_")
    if kind not in ("time", "peakmem") or func not in tests.get(module, set()):
        return None
    if bench["name"] in codspeed.get("skip", []):
        return None
    pinned = codspeed.get("params", {})
    ids = "-".join(pinned.get(a["name"]) or str(a.get("labels", a["values"])[0]) for a in reversed(bench["params"]))
    case = f"test_{func}[{ids}]" if ids else f"test_{func}"
    return f"{CODSPEED}/benchmarks/benchmarks/codspeed/test_{subject}.py::{quote(case)}?runnerMode=Simulation"


def link(groups: list[dict], catalog: "Catalog", sources: dict[str, str], links: dict, codspeed: dict) -> None:
    """Add LINKS' pages (descriptions.toml) to groups and environments, and each benchmark's source.

    An environment links the solver its label starts with: "UMFPACK, MKL" links UMFPACK.
    """
    for g in groups:
        page = links.get("groups", {}).get(g["name"], {})
        if page.get("docs"):
            g["url"] = page["docs"]
        if shown := [{"name": n, "url": page[k]} for k, n in GROUP_LINKS if page.get(k)]:
            g["links"] = shown
    for env in catalog.envs.values():
        if url := links.get("solvers", {}).get(re.split(r",| on | · ", env.get("label", ""))[0]):
            env["url"] = url
    root = Path(__file__).resolve().parents[1]
    names = {g["id"]: g["name"] for g in groups}
    tests: dict[str, dict[str, set[str]]] = {}
    for bench in catalog.benchmarks.values():
        folder = sources.get(bench["group"])
        source = f"{folder}/{bench['name'].split('.')[0]}.py"
        if folder and (root / source).is_file():
            bench["url"] = f"{REPO}/blob/main/{source}"
        subject = names[bench["group"]]
        if subject not in tests:
            tests[subject] = codspeed_tests(subject, root)
        if url := codspeed_url(bench, subject, tests[subject], codspeed):
            bench["codspeed"] = url


def profile_url(path: Path, value: str) -> str:
    """A finding's `profile` as a URL: an https URL as given, else a file of PROFILES that must exist."""
    if value.startswith("https://"):
        return value
    name = value.removeprefix("profiles/")
    if "/" in name or not name.endswith(".html") or not (PROFILES / name).is_file():
        msg = f"{path.name}: profile {value} is neither an https URL nor an .html file in profiles/"
        raise SystemExit(msg)
    return f"{PUBLIC_BASE}profiles/{quote(name)}"


def findings(index: dict) -> list[dict]:
    """FINDINGS' entries, each naming its benchmark's id and a label per axis.

    A finding about a group this export lacks is left out; one that names a benchmark, parameter or
    value its group lacks fails the export, as its link would open the wrong history.
    """
    path = FINDINGS
    groups = {g["name"]: g["id"] for g in index["groups"]}
    out = []
    for f in tomllib.loads(path.read_text())["findings"]:
        if f["group"] not in groups:
            continue
        bench = next(
            (b for b in index["benchmarks"] if b["group"] == groups.get(f["group"]) and b["name"] == f["benchmark"]),
            None,
        )
        if bench is None:
            msg = f"{path.name}: no benchmark {f['benchmark']} in {f['group']}"
            raise SystemExit(msg)
        names = [axis["name"] for axis in bench["params"]]
        if unknown := set(f["params"]) - set(names):
            msg = f"{path.name}: {f['benchmark']} has no parameter {', '.join(sorted(unknown))}"
            raise SystemExit(msg)
        params = []
        for axis in bench["params"]:
            value = f["params"].get(axis["name"], "")
            if value and value not in axis.get("labels", axis["values"]):
                msg = f"{path.name}: {f['benchmark']}'s {axis['name']} has no value {value}"
                raise SystemExit(msg)
            params.append(value)
        out.append(
            {
                "title": f["title"],
                "text": f["text"],
                "benchmark": bench["id"],
                "params": params,
                "url": f"{REPO}/blob/main/docs/findings.md#{f['doc']}",
            }
            | ({"profile": profile_url(path, f["profile"])} if "profile" in f else {})
        )
    return out


# (case, machine, measure) -> one (commit, value, spread or None) per commit, oldest first
Series = dict[tuple[str, str, str], list[tuple[str, float, float | None]]]


def release_changes(series: Series, released: set[str]) -> list[dict]:
    """Moves between two releases in a row that are larger than the case's noise (module docstring)."""
    out = []
    for (case, machine, measure), points in series.items():
        kept = [p for p in points if p[0] in released]
        for (old, a, sa), (new, b, sb) in itertools.pairwise(kept):
            threshold = noise_threshold(sa, sb)
            if a > 0 and abs(b / a - 1) > threshold:
                out.append(
                    change(case, machine, measure, old, new, b / a, "release") | {"threshold": round(threshold, 4)}
                )
    return out


def otava(values: list[list[float]]) -> list[list[dict]]:
    """scripts/change_points.py on each series of VALUES, in Otava's own environment."""
    uv = shutil.which("uv")
    if uv is None:
        sys.exit("export_ui: change points need uv (https://docs.astral.sh/uv/)")
    run = subprocess.run(  # noqa: S603 - our own script, with JSON on stdin
        [uv, "run", "--quiet", "--locked", "--script", str(CHANGE_POINTS), str(NOISE_FLOOR)],
        input=json.dumps(values),
        capture_output=True,
        text=True,
        check=False,
    )
    if run.returncode:
        sys.exit(f"export_ui: change_points.py exited {run.returncode}: {run.stderr.strip()}")
    return json.loads(run.stdout)


def change_points(series: Series) -> list[dict]:
    """Otava's change points along each series (module docstring)."""
    keys = list(series)
    found = otava([[v for _, v, _ in series[k]] for k in keys])
    out = []
    for (case, machine, measure), points in zip(keys, found, strict=True):
        commits = [c for c, _, _ in series[case, machine, measure]]
        for p in points:
            i = p["index"]
            out.append(
                change(case, machine, measure, commits[i - 1], commits[i], p["ratio"], "change-point")
                | {"pvalue": float(f"{p['pvalue']:.3g}")}
            )
    return out


def change(case: str, machine: str, measure: str, baseline: str, commit: str, ratio: float, method: str) -> dict:
    """One entry of the index's changes."""
    return {
        "case": case,
        "machine": machine,
        "measure": measure,
        "commit": commit,
        "baseline": baseline,
        "ratio": round(ratio, 4),
        "method": method,
    }


def ordered(changes: list[dict], series: Series) -> list[dict]:
    """CHANGES grouped by series, each series oldest first, as the schema promises."""
    at = {key: {c: i for i, (c, _, _) in enumerate(points)} for key, points in series.items()}

    def key(c: dict) -> tuple:
        s = (c["case"], c["machine"], c["measure"])
        return (*s, at[s][c["commit"]], c["method"])

    return sorted(changes, key=key)


def export(results: Path, out: Path) -> dict:
    """Write the index and reports, and return the index. OUT/reports/ is emptied first."""
    for path in (out, out / "index.json", out / "reports"):
        output_path(path)
    # A report from an earlier export that this one does not list would linger unseen.
    shutil.rmtree(out / "reports", ignore_errors=True)
    groups, commits, reports = [], [], []
    sources: dict[str, str] = {}  # group -> its benchmarks' folder in this repository
    series: Series = {}
    machines: dict[str, dict] = {}
    catalog = Catalog()
    for meta in sorted(results.glob("*/benchmarks.json")):
        subject = meta.parent.name
        group = slug(subject)
        conf_file = Path(f"asv/{subject}.json")
        conf = json.loads(conf_file.read_text()) if conf_file.exists() else {}
        groups.append({"id": group, "name": subject} | ({"url": conf["project_url"]} if "project_url" in conf else {}))
        sources[group] = conf.get("benchmark_dir", "").removeprefix("../")
        info = {k: v for k, v in json.loads(meta.read_text()).items() if isinstance(v, dict)}  # skips "version"
        dates: dict[str, int] = {}
        found: list[tuple[str, str, dict]] = []  # (machine id, commit, report)
        for (machine, commit), files in sorted(runs(meta.parent).items()):
            report = catalog.report(subject, files, info)
            if not report:
                continue
            machine_id = machines.setdefault(machine, {"id": slug(machine), "name": machine})["id"]
            found.append((machine_id, commit, report))
            dates[commit] = max(dates.get(commit, 0), *(f["date"] for f in files))
            path = f"reports/{group}/{machine_id}/{commit}.json"
            write(out / path, report)
            reports.append(
                {"path": path, "format": REPORT_FORMAT, "group": group, "machine": machine_id, "commit": commit}
            )
        catalog.order(subject, info)
        envs = [e for (s, _), e in catalog.envs.items() if s == subject]
        for env, text in zip(envs, solver_labels([e["name"] for e in envs]) or [], strict=False):
            env["label"] = text
        tags = releases(subject, "export_ui")
        for commit, date in sorted(dates.items(), key=lambda c: (c[1], c[0])):
            tag = tags.get(commit[:8])
            commits.append({"id": commit, "group": group, "date": iso(date)} | ({"release": tag} if tag else {}))
        order = {c: (d, c) for c, d in dates.items()}
        for machine_id, commit, report in sorted(found, key=lambda f: order[f[1]]):
            for case, metric in report.items():
                for measure, m in metric.items():
                    series.setdefault((case, machine_id, measure), []).append((commit, m["value"], spread(m)))
    released = {c["id"] for c in commits if "release" in c}
    about = tomllib.loads(DESCRIPTIONS.read_text())
    describe(list(catalog.benchmarks.values()), about)
    link(groups, catalog, sources, about.get("links", {}), about.get("codspeed", {}))
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
        "changes": ordered(release_changes(series, released) + change_points(series), series),
    }
    index["findings"] = findings(index)
    write(out / "index.json", index)
    return index


if __name__ == "__main__":
    index = export(Path(sys.argv[1]), Path(sys.argv[2]))
    counts = ", ".join(f"{len(index[k])} {k}" for k in ("groups", "benchmarks", "cases", "commits", "reports"))
    print(f"export_ui: {counts}", file=sys.stderr)
