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
  group?: string;
  direction?: string;
  page?: string;
  platform?: string;
  python?: string;
  check?: string;
  /** The benchmark search a static page hands over; the viewer reads it once and drops it on the first move. */
  q?: string;
}

export function readView(search: string, hash = ""): View {
  const q = new URLSearchParams(search);
  const view: View = { params: q.getAll("p") };
  for (const key of [
    "bench",
    "measure",
    "machine",
    "group",
    "direction",
    "page",
    "platform",
    "python",
    "check",
    "q",
  ] as const) {
    const value = q.get(key);
    if (value) view[key] = value;
  }
  // The old asv homepage's section anchors.
  if (!search && hash === "#works-together") view.page = "compatibility";
  if (!search && hash === "#latest-release") view.page = "changes";
  return view;
}

export function writeView(view: View): string {
  const q = new URLSearchParams();
  if (view.bench) q.set("bench", view.bench);
  for (const p of view.params) q.append("p", p);
  if (view.measure) q.set("measure", view.measure);
  if (view.machine) q.set("machine", view.machine);
  if (view.group) q.set("group", view.group);
  if (view.direction && view.direction !== "all") q.set("direction", view.direction);
  for (const key of ["page", "platform", "python", "check", "q"] as const) {
    if (view[key]) q.set(key, view[key]);
  }
  const text = q.toString();
  return text ? `?${text}` : "";
}

/** Each axis's shown labels, which the URL uses. */
export function axisLabels(bench: Benchmark): string[][] {
  return bench.params.map((axis) => axis.labels ?? axis.values);
}

/** The shown label of each of VALUES, one per axis of BENCH. */
export function paramLabels(bench: Benchmark, values: string[]): string[] {
  return bench.params.map((axis, i) => {
    const v = values[i] ?? "";
    return axis.labels?.[axis.values.indexOf(v)] ?? v;
  });
}

/** A commit's name: its release, or its short hash. */
export function commitName(c: { id: string; release?: string | undefined }): string {
  return c.release ?? c.id.slice(0, 8);
}

/** A release change's noise threshold, as the tables and the tip show it. */
export function noiseText(c: { threshold?: number | undefined }): string {
  return `±${((c.threshold ?? 0) * 100).toFixed(1)}%`;
}

/** The parameter values VIEW picks for BENCH: each axis's first value where the URL names none it has. */
export function pickParams(bench: Benchmark, wanted: string[]): string[] {
  return bench.params.map((axis, i) => {
    const labels = axis.labels ?? axis.values;
    const at = labels.indexOf(wanted[i] ?? "");
    return axis.values[Math.max(at, 0)] ?? "";
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

/** What to call each environment: the labels the data gives when they tell all of them apart, else shortNames. */
export function displayNames(envs: { name: string; label?: string }[]): string[] {
  const labels = envs.map((e) => e.label);
  if (labels.every((l): l is string => Boolean(l)) && new Set(labels).size === labels.length) return labels;
  return shortNames(envs.map((e) => e.name));
}

export interface Point {
  commit: string;
  /** Position along the x axis: the commit's place in its group, oldest first. */
  at: number;
  label: string;
  /** Whether the commit has a release name, which the axis prefers to show. */
  released: boolean;
  date: string;
  env: string;
  value: number;
  lower?: number;
  upper?: number;
  /** How far, as a fraction of the value, the measure's noise rule lets the value move. */
  noise?: number;
}

export interface Line {
  env: string;
  name: string;
  short: string;
  case: string;
  points: Point[];
}

/** The middle half of the samples over the value, as the exporter's spread(); 0 where that is not a number. */
function spread(m: { value: number; lower_value?: number; upper_value?: number }): number {
  const s = ((m.upper_value ?? Number.NaN) - (m.lower_value ?? Number.NaN)) / m.value;
  return m.value > 0 && Number.isFinite(s) ? s : 0;
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
  const envs = new Map(index.environments.map((e) => [e.id, e]));
  const rule = index.measures.find((m) => m.id === measure)?.noise;
  const cases = index.cases.filter(
    (c) => c.benchmark === bench.id && c.params.length === params.length && c.params.every((p, i) => p === params[i]),
  );
  const found = cases.map((c) => ({
    env: c.environment,
    name: envs.get(c.environment)?.name ?? c.environment,
    label: envs.get(c.environment)?.label,
    case: c.id,
    points: commits.flatMap((commit, at): Point[] => {
      const metric = reports.get(commit.id)?.[c.id]?.[measure];
      if (!metric) return [];
      return [
        {
          commit: commit.id,
          at,
          label: commitName(commit),
          released: commit.release !== undefined,
          date: commit.date.slice(0, 10),
          env: c.environment,
          value: metric.value,
          ...(metric.lower_value === undefined ? {} : { lower: metric.lower_value }),
          ...(metric.upper_value === undefined ? {} : { upper: metric.upper_value }),
          ...(rule && { noise: Math.max(rule.floor, rule.spreads * spread(metric)) }),
        },
      ];
    }),
  }));
  const kept = found.filter((l) => l.points.length > 0).sort((a, b) => a.name.localeCompare(b.name));
  const short = displayNames(kept.map((l) => (l.label ? { name: l.name, label: l.label } : { name: l.name })));
  return kept.map(({ label: _, ...l }, i) => ({ ...l, short: short[i] ?? l.name }));
}

/**
 * Each line's series colour, 0 to 7: its environment label's place among the index's labels, so a
 * label (a solver) has one colour on every chart and story. By the line's place instead when a line
 * has no label or two lines would share a colour.
 */
export function seriesSlots(index: Pick<BenchmarkIndex, "environments">, shown: Pick<Line, "env">[]): number[] {
  const labels = [...new Set(index.environments.flatMap((e) => (e.label ? [e.label] : [])))];
  const label = new Map(index.environments.map((e) => [e.id, e.label]));
  const slots = shown.map((l) => labels.indexOf(label.get(l.env) ?? "") % 8);
  return slots.includes(-1) || new Set(slots).size < slots.length ? shown.map((_, i) => i % 8) : slots;
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
  way: ReturnType<typeof verdict>;
}

/** The release changes into each group's newest release for the start page: worse first, then by size. */
export function latestChanges(index: BenchmarkIndex): LatestChange[] {
  const commits = new Map(index.commits.map((c) => [c.id, c]));
  const newest = new Map<string, string>();
  for (const c of index.commits) if (c.release) newest.set(c.group, c.id); // oldest first, so the last wins
  const cases = new Map(index.cases.map((c) => [c.id, c]));
  const benches = new Map(index.benchmarks.map((b) => [b.id, b]));
  const groups = new Map(index.groups.map((g) => [g.id, g]));
  const measures = new Map(index.measures.map((m) => [m.id, m]));
  const envs = new Map<string, string>();
  for (const g of index.groups) {
    const mine = index.environments.filter((e) => e.group === g.id);
    const short = displayNames(mine);
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
    const name = (id: string) => commitName(commits.get(id) ?? { id });
    const params = paramLabels(bench, c.params);
    const env = envs.get(c.environment) ?? c.environment;
    const way = verdict(change.ratio, measures.get(change.measure)?.better);
    out.push({ change, group, bench, params, env, from: name(change.baseline), to: name(change.commit), way });
  }
  const rank = { worse: 0, moved: 1, better: 2 };
  const size = (r: LatestChange) => Math.abs(Math.log(r.change.ratio));
  return out.sort((a, b) => rank[a.way] - rank[b.way] || size(b) - size(a));
}

export interface ChangeGroup {
  bench: Benchmark;
  group: BenchmarkIndex["groups"][number];
  rows: LatestChange[];
}

/** ROWS gathered per benchmark and machine, in the order each first appears; rows keep their order. */
export function byBenchmark(rows: LatestChange[]): ChangeGroup[] {
  const out = new Map<string, ChangeGroup>();
  for (const row of rows) {
    const key = `${row.bench.id}/${row.change.machine}`;
    const found = out.get(key);
    if (found) found.rows.push(row);
    else out.set(key, { bench: row.bench, group: row.group, rows: [row] });
  }
  return [...out.values()];
}

/** One benchmark's changes as Setup and Benchmarks both show them: "−80%", or "−79% to −80%" over ROWS, largest last. */
export function percentRange(rows: LatestChange[]): string {
  const top = rows[0];
  const low = rows[rows.length - 1];
  if (!top || !low) return "";
  return rows.length > 1 ? `${percent(low.change.ratio)} to ${percent(top.change.ratio)}` : percent(top.change.ratio);
}

/** TEXT cut after each "." and "_", so a long dotted or snake_case name can break there (<wbr>). */
export function breakable(text: string): string[] {
  return text.split(/(?<=[._])/);
}

/** Up to MOST tick labels, evenly spaced, from the release-named points if there are any. */
export function ticksFor(steps: { label: string; released: boolean }[], most: number): string[] {
  const named = steps.filter((s) => s.released);
  const pool = (named.length > 1 ? named : steps).map((s) => s.label);
  const count = Math.max(2, Math.floor(most));
  if (steps.length <= count) return steps.map((s) => s.label);
  if (pool.length <= count) return pool;
  return Array.from({ length: count }, (_, i) => pool[Math.round((i * (pool.length - 1)) / (count - 1))] ?? "");
}

/** A p-value as the tables show it: "p < 0.001" below that, else two significant figures. */
export function pText(p: number | undefined): string {
  if (p === undefined) return "p unknown";
  return p < 0.001 ? "p < 0.001" : `p = ${p.toPrecision(2)}`;
}

/** A readable fallback for benchmark identifiers; the original name stays available in the detail view. */
export function benchmarkLabel(name: string): string {
  const parts = name.split(".");
  const method = parts.pop() ?? name;
  const owner = parts.length > 1 ? (parts.pop() ?? "") : "";
  const words = (text: string) => text.replace(/([a-z0-9])([A-Z])/g, "$1 $2").replaceAll("_", " ");
  const action = words(method.replace(/^(timeraw|time|peakmem|track)_/, ""));
  const context = words(owner);
  const own = context.toLowerCase().split(" ");
  const repeated = action.split(" ").filter((w) => own.includes(w.toLowerCase())).length;
  // "Multi Scores", not "Multi Scores · scores"; "First score", not "Single Score · first score".
  const label = !context
    ? action
    : repeated === action.split(" ").length
      ? context
      : repeated
        ? action
        : `${context} · ${action}`;
  const text = label.charAt(0).toUpperCase() + label.slice(1);
  return method.startsWith("peakmem_") ? `${text} · Peak memory` : text;
}

/** What to call BENCH: the data's label, else a readable form of its name; with the name too when another in its group reads the same. */
export function benchLabel(index: BenchmarkIndex, bench: Benchmark): string {
  const text = (b: Benchmark) => b.label ?? benchmarkLabel(b.name);
  const own = text(bench);
  const clash = index.benchmarks.some((b) => b !== bench && b.group === bench.group && text(b) === own);
  return clash ? `${own} (${bench.name})` : own;
}

/**
 * The two pages: Setup ("home") and Benchmarks ("explorer"). Older links keep working: the
 * compatibility view is part of Setup, and release changes open the Benchmarks overview.
 */
export function pageOf(view: View): "home" | "explorer" {
  if (view.bench || view.page === "explorer" || view.page === "changes") return "explorer";
  if (!view.page && (view.group || view.direction)) return "explorer";
  return "home";
}

/** The benchmark VIEW names: by id, or by name within the group view.group names (old asv links). */
export function findBench(index: BenchmarkIndex, view: View): Benchmark | undefined {
  if (!view.bench) return undefined;
  const byId = index.benchmarks.find((b) => b.id === view.bench);
  if (byId) return byId;
  const group = index.groups.find((g) => g.name === view.group || g.id === view.group);
  return index.benchmarks.find((b) => b.name === view.bench && (!group || b.group === group.id));
}

/** One case's values in MEASURE along REPORTS (commit -> report), in GROUP's commit order. */
export function seriesOf(
  index: BenchmarkIndex,
  reports: Map<string, BenchmarkReport>,
  caseId: string,
  measure: string,
  group: string,
) {
  return index.commits
    .filter((c) => c.group === group)
    .flatMap((c) => {
      const value = reports.get(c.id)?.[caseId]?.[measure]?.value;
      return value === undefined ? [] : [{ commit: c.id, value, released: c.release !== undefined }];
    });
}
