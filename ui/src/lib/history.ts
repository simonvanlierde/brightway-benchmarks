// What a benchmark's page shows, worked out from the index and its reports: no fetching, no DOM.
import type { BenchmarkIndex, BenchmarkReport, Change } from "./contract";

type Benchmark = BenchmarkIndex["benchmarks"][number];
type Measure = BenchmarkIndex["measures"][number];

/** What the URL holds: the page's whole state, so a link opens the same view. */
export interface View {
  bench?: string;
  /** One label (or value) per parameter axis, in the benchmark's order. */
  params: string[];
  measure?: string;
  machine?: string;
}

export function readView(search: string): View {
  const q = new URLSearchParams(search);
  const view: View = { params: q.getAll("p") };
  for (const key of ["bench", "measure", "machine"] as const) {
    const value = q.get(key);
    if (value) view[key] = value;
  }
  return view;
}

export function writeView(view: View): string {
  const q = new URLSearchParams();
  if (view.bench) q.set("bench", view.bench);
  for (const p of view.params) q.append("p", p);
  if (view.measure) q.set("measure", view.measure);
  if (view.machine) q.set("machine", view.machine);
  const text = q.toString();
  return text ? `?${text}` : "";
}

/** Each axis's shown labels, which the URL uses. */
export function axisLabels(bench: Benchmark): string[][] {
  return bench.params.map((axis) => axis.labels ?? axis.values);
}

/** The parameter values VIEW picks for BENCH: each axis's first value where the URL names none it has. */
export function pickParams(bench: Benchmark, wanted: string[]): string[] {
  return bench.params.map((axis, i) => {
    const labels = axis.labels ?? axis.values;
    const at = labels.indexOf(wanted[i] ?? "");
    return axis.values[at >= 0 ? at : 0] ?? "";
  });
}

/**
 * Short names for environments that share most of their name, such as solver variants of one
 * Python stack: the dash-separated words not every one of them has. "default" when nothing is left.
 */
export function shortNames(names: string[]): string[] {
  const words = names.map((n) => n.split("-"));
  const shared = words.length > 1 ? words.reduce((acc, w) => acc.filter((x) => w.includes(x))) : [];
  const short = words.map((w) => w.filter((x) => !shared.includes(x)).join(" ") || "default");
  return new Set(short).size === short.length ? short : names;
}

export interface Point {
  commit: string;
  /** Position along the x axis: the commit's place in its group, oldest first. */
  at: number;
  label: string;
  date: string;
  env: string;
  value: number;
  lower?: number;
  upper?: number;
}

export interface Line {
  env: string;
  name: string;
  short: string;
  case: string;
  points: Point[];
}

/** One line per environment for BENCH at PARAMS in MEASURE, from the reports by commit. */
export function lines(
  index: BenchmarkIndex,
  bench: Benchmark,
  params: string[],
  measure: string,
  reports: Map<string, BenchmarkReport>,
): Line[] {
  const commits = index.commits.filter((c) => c.group === bench.group);
  const envNames = new Map(index.environments.map((e) => [e.id, e.name]));
  const cases = index.cases.filter(
    (c) => c.benchmark === bench.id && c.params.length === params.length && c.params.every((p, i) => p === params[i]),
  );
  const found = cases.map((c) => ({
    env: c.environment,
    name: envNames.get(c.environment) ?? c.environment,
    case: c.id,
    points: commits.flatMap((commit, at): Point[] => {
      const metric = reports.get(commit.id)?.[c.id]?.[measure];
      if (!metric) return [];
      return [
        {
          commit: commit.id,
          at,
          label: commit.release ?? commit.id.slice(0, 8),
          date: commit.date.slice(0, 10),
          env: c.environment,
          value: metric.value,
          ...(metric.lower_value === undefined ? {} : { lower: metric.lower_value }),
          ...(metric.upper_value === undefined ? {} : { upper: metric.upper_value }),
        },
      ];
    }),
  }));
  const kept = found.filter((l) => l.points.length > 0).sort((a, b) => a.name.localeCompare(b.name));
  const short = shortNames(kept.map((l) => l.name));
  return kept.map((l, i) => ({ ...l, short: short[i] ?? l.name }));
}

/** The changes on LINES in MEASURE on MACHINE. */
export function changesFor(index: BenchmarkIndex, lines: Line[], measure: string, machine: string): Change[] {
  const cases = new Set(lines.map((l) => l.case));
  return (index.changes ?? []).filter((c) => cases.has(c.case) && c.measure === measure && c.machine === machine);
}

/** Whether a change is worse or better, by the measure's direction; "moved" when it has none. */
export function verdict(ratio: number, better: Measure["better"] | undefined): "worse" | "better" | "moved" {
  if (!better) return "moved";
  return ratio > 1 === (better === "lower") ? "worse" : "better";
}

/** "+12%" or "−8.4%": whole percents from 2% up, one decimal below. */
export function percent(ratio: number): string {
  const p = (ratio - 1) * 100;
  const text = Math.abs(p) < 2 ? Math.abs(p).toFixed(1) : Math.abs(p).toFixed(0);
  return `${p < 0 ? "−" : "+"}${text}%`;
}

const SCALES: Record<string, [number, string][]> = {
  ns: [
    [1e9, "s"],
    [1e6, "ms"],
    [1e3, "µs"],
    [1, "ns"],
  ],
  B: [
    [1e9, "GB"],
    [1e6, "MB"],
    [1e3, "kB"],
    [1, "B"],
  ],
};

/** A unit for values around TYPICAL, as [divisor, unit name]: the largest that keeps it at 1 or more. */
export function scaleFor(unit: string, typical: number): [number, string] {
  const steps = SCALES[unit];
  if (!steps) return [1, unit];
  return steps.find(([d]) => typical >= d) ?? steps[steps.length - 1] ?? [1, unit];
}

/** VALUE in UNIT, to three significant figures, in its own best scale. */
export function format(value: number, unit: string): string {
  const [d, name] = scaleFor(unit, Math.abs(value));
  return `${sig(value / d)} ${name}`;
}

/** Three significant figures, without exponent notation. */
export function sig(x: number): string {
  if (x === 0 || !Number.isFinite(x)) return String(x);
  const digits = Math.max(0, 2 - Math.floor(Math.log10(Math.abs(x))));
  return x.toFixed(Math.min(digits, 6));
}

export interface LatestChange {
  change: Change;
  group: BenchmarkIndex["groups"][number];
  bench: Benchmark;
  params: string[];
  env: string;
  from: string;
  to: string;
}

/** The release changes into each group's newest release, largest first, for the start page. */
export function latestChanges(index: BenchmarkIndex): LatestChange[] {
  const commits = new Map(index.commits.map((c) => [c.id, c]));
  const newest = new Map<string, string>();
  for (const c of index.commits) if (c.release) newest.set(c.group, c.id); // oldest first, so the last wins
  const cases = new Map(index.cases.map((c) => [c.id, c]));
  const benches = new Map(index.benchmarks.map((b) => [b.id, b]));
  const groups = new Map(index.groups.map((g) => [g.id, g]));
  const envs = new Map<string, string>();
  for (const g of index.groups) {
    const mine = index.environments.filter((e) => e.group === g.id);
    const short = shortNames(mine.map((e) => e.name));
    mine.forEach((e, i) => {
      envs.set(e.id, short[i] ?? e.name);
    });
  }
  const out: LatestChange[] = [];
  for (const change of index.changes ?? []) {
    const c = cases.get(change.case);
    const bench = c && benches.get(c.benchmark);
    const group = bench && groups.get(bench.group);
    if (!c || !bench || !group || change.method !== "release" || newest.get(group.id) !== change.commit) continue;
    const name = (id: string) => commits.get(id)?.release ?? id.slice(0, 8);
    const labels = axisLabels(bench);
    const params = c.params.map((v, i) => labels[i]?.[bench.params[i]?.values.indexOf(v) ?? -1] ?? v);
    const env = envs.get(c.environment) ?? c.environment;
    out.push({ change, group, bench, params, env, from: name(change.baseline), to: name(change.commit) });
  }
  return out.sort((a, b) => Math.abs(Math.log(b.change.ratio)) - Math.abs(Math.log(a.change.ratio)));
}
