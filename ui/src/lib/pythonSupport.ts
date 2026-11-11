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
 * The supported Pythons (`eol` false) or the end-of-life ones (true) as a table: the full grid the
 * probe runs, so a result that is missing is an empty cell. Undefined when the data lists none.
 */
export function supportTable(
  support: Omit<PythonSupport, "results" | "pythons"> & {
    results: SupportResult[];
    pythons: PythonSupport["pythons"][number][];
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
  const failures = new Map<string, SupportFailure>();
  for (const r of results.filter((x) => x.status === "fail")) {
    const reason = r.reason ?? "failed";
    const f = failures.get(reason) ?? { reason, pythons: [], platforms: [], packages: [] };
    f.pythons = unique([...f.pythons, r.python]).sort(numeric);
    f.platforms = platforms.filter((p) => p === r.platform || f.platforms.includes(p)); // in grid order
    f.packages = unique([...f.packages, r.package]);
    failures.set(reason, f);
  }
  return {
    pythons: pythons.map((p) => p.version),
    rows: [...rows.values()],
    failures: [...failures.values()],
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
