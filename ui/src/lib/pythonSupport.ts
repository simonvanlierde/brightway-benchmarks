import type { Guidance } from "./contract";

export type PythonSupport = NonNullable<Guidance["pythonSupport"]>;
export type SupportResult = PythonSupport["results"][number];

export interface SupportRow {
  package: string;
  platform: string;
  cells: Map<string, SupportResult>;
}
export interface SupportFailure {
  reason: string;
  pythons: string[];
  platforms: string[];
  packages: string[];
}
export interface SupportTable {
  pythons: string[];
  rows: SupportRow[];
  failures: SupportFailure[];
  /** The oldest result's date: the table is only as fresh as its stalest cell. */
  checked: string;
  /** The run behind the oldest result, linked once beside its date. */
  run: string;
}

const numeric = (a: string, b: string) => a.localeCompare(b, "en", { numeric: true });
const unique = (values: string[]) => [...new Set(values)];

/**
 * One line per reason, for the combinations that failed with it and no others. Results merge into a line
 * only where they share the reason, Python and platforms (more packages), and then the reason, packages
 * and platforms (more Pythons), so a line's Pythons x platforms x packages is exactly what failed.
 */
function failureLines(packages: string[], platforms: string[], results: SupportResult[]): SupportFailure[] {
  const failed = new Map<string, { reason: string; python: string; package: string; platforms: string[] }>();
  for (const r of results.filter((x) => x.status === "fail")) {
    const reason = r.reason ?? "failed";
    const key = `${reason}\u0000${r.python}\u0000${r.package}`;
    const f = failed.get(key) ?? { reason, python: r.python, package: r.package, platforms: [] };
    f.platforms = platforms.filter((p) => p === r.platform || f.platforms.includes(p)); // in grid order
    failed.set(key, f);
  }
  const byPython = new Map<string, SupportFailure>();
  for (const f of failed.values()) {
    const key = `${f.reason}\u0000${f.python}\u0000${f.platforms.join()}`;
    const line = byPython.get(key) ?? { reason: f.reason, pythons: [f.python], platforms: f.platforms, packages: [] };
    line.packages = packages.filter((p) => p === f.package || line.packages.includes(p));
    byPython.set(key, line);
  }
  const merged = new Map<string, SupportFailure>();
  for (const f of byPython.values()) {
    const key = `${f.reason}\u0000${f.packages.join()}\u0000${f.platforms.join()}`;
    const line = merged.get(key) ?? { ...f, pythons: [] };
    line.pythons = unique([...line.pythons, ...f.pythons]).sort(numeric);
    merged.set(key, line);
  }
  return [...merged.values()];
}

/**
 * The supported Pythons (`eol` false) or the end-of-life ones (true) as a table: the full grid the
 * probe runs, so a result that is missing is an empty cell. Undefined when the data lists none.
 */
export function supportTable(
  support: Omit<PythonSupport, "results" | "pythons"> & {
    results: SupportResult[];
    pythons: { version: string; endOfLife: boolean; platforms: string[] }[];
  },
  eol: boolean,
): SupportTable | undefined {
  const pythons = support.pythons.filter((p) => p.endOfLife === eol);
  if (pythons.length === 0) return undefined;
  const shown = new Set(pythons.map((p) => p.version));
  const results = support.results.filter((r) => shown.has(r.python));
  const rows = new Map<string, SupportRow>();
  const platforms = unique(pythons.flatMap((p) => p.platforms));
  for (const package_ of support.packages) {
    for (const platform of platforms) {
      rows.set(`${package_} ${platform}`, { package: package_, platform, cells: new Map() });
    }
  }
  for (const r of results) rows.get(`${r.package} ${r.platform}`)?.cells.set(r.python, r);
  const oldest = results.toSorted((a, b) => a.date.localeCompare(b.date))[0];
  return {
    pythons: pythons.map((p) => p.version),
    rows: [...rows.values()],
    failures: failureLines(support.packages, platforms, results),
    checked: oldest?.date ?? "",
    run: oldest?.run ?? "",
  };
}

/** "3.11 to 3.14" for three or more Pythons in a row of ALL, else "3.11 and 3.13". */
function span(some: string[], all: string[]): string {
  const first = all.indexOf(some[0] ?? "");
  const inRow = some.every((p, i) => all[first + i] === p);
  return some.length > 2 && inRow ? `${some[0]} to ${some.at(-1)}` : listed(some);
}

/**
 * One line from the table: which Pythons work on every system, which work where they were checked,
 * and why each other one fails. Counts only the cells that hold a result; empty when none passed or failed.
 */
export function supportLead(table: SupportTable, label: (platform: string) => string = (p) => p): string {
  const cells = (python: string) => table.rows.map((r) => r.cells.get(python));
  const checked = (python: string) => cells(python).filter((c) => c !== undefined);
  const working = table.pythons.filter((p) => cells(p).every((c) => c?.status === "pass"));
  const out = working.length
    ? [`${span(working, table.pythons)} ${working.length > 1 ? "work" : "works"} on every system.`]
    : [];
  let reasons = false;
  for (const python of table.pythons.filter((p) => !working.includes(p))) {
    const all = checked(python);
    const failed = all.filter((c) => c.status === "fail");
    if (failed.length === 0) {
      if (all.length === 0 || all.some((c) => c.status !== "pass")) continue; // nothing failed, or not declared
      const unchecked = unique(table.rows.filter((r) => !r.cells.has(python)).map((r) => r.platform));
      out.push(`${python} works where checked; not checked on ${listed(unchecked.map(label))}.`);
      continue;
    }
    // uv's message for a dependency that does not compile: "Failed to build `name==version`: ...".
    const built = new Set(failed.map((c) => c.reason?.match(/^Failed to build `?([\w.-]+?)(?:==[^`:\s]*)?`?:/)?.[1]));
    const [dependency] = built;
    if (failed.length === all.length && built.size === 1 && dependency) {
      out.push(`${python} does not install yet: a dependency (${dependency}) fails to build.`);
      continue;
    }
    reasons = true;
    out.push(
      failed.length === all.length
        ? `${python} fails everywhere it was checked.`
        : `${python} fails for ${failed.length} of ${all.length} packages and systems.`,
    );
  }
  if (reasons) out.push("The reasons are below the table.");
  return out.join(" ");
}

/** A failure reason in parts, the names it quotes in backticks as code. */
export function codeParts(reason: string): { text: string; code: boolean }[] {
  return reason
    .split("`")
    .map((text, i) => ({ text, code: i % 2 === 1 }))
    .filter((p) => p.text);
}

const WORDS = { pass: "Passed", fail: "Failed", undeclared: "Not declared" } as const;
/** The word a cell shows: colour never carries the result alone. */
export const supportWord = (status: SupportResult["status"]) => WORDS[status];

/** "a, b and c" */
export function listed(items: string[]): string {
  return items.length < 2 ? items.join("") : `${items.slice(0, -1).join(", ")} and ${items.at(-1)}`;
}
