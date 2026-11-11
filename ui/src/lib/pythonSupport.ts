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
  return {
    pythons: pythons.map((p) => p.version),
    rows: [...rows.values()],
    failures: failureLines(support.packages, platforms, results),
    checked: results.map((r) => r.date).sort()[0] ?? "",
  };
}

const WORDS = { pass: "Pass", fail: "Failed", undeclared: "Not declared" } as const;
/** The word a cell shows: colour never carries the result alone. */
export const supportWord = (status: SupportResult["status"]) => WORDS[status];

/** "a, b and c" */
export function listed(items: string[]): string {
  return items.length < 2 ? items.join("") : `${items.slice(0, -1).join(", ")} and ${items.at(-1)}`;
}
