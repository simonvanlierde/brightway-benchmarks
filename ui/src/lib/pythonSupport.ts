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

/** The supported Pythons (`eol` false) or the end-of-life ones (true) as a table; undefined when none has a result. */
export function supportTable(
  support: Omit<PythonSupport, "results"> & { results: SupportResult[] },
  eol: boolean,
): SupportTable | undefined {
  const results = support.results.filter((r) => support.endOfLife.includes(r.python) === eol);
  if (results.length === 0) return undefined;
  const rows = new Map<string, SupportRow>();
  for (const package_ of support.packages) {
    for (const platform of unique(results.map((r) => r.platform))) {
      rows.set(`${package_} ${platform}`, { package: package_, platform, cells: new Map() });
    }
  }
  for (const r of results) rows.get(`${r.package} ${r.platform}`)?.cells.set(r.python, r);
  const failures = new Map<string, SupportFailure>();
  for (const r of results.filter((x) => x.status === "fail")) {
    const reason = r.reason ?? "failed";
    const f = failures.get(reason) ?? { reason, pythons: [], platforms: [], packages: [] };
    f.pythons = unique([...f.pythons, r.python]).sort(numeric);
    f.platforms = unique([...f.platforms, r.platform]);
    f.packages = unique([...f.packages, r.package]);
    failures.set(reason, f);
  }
  return {
    pythons: unique(results.map((r) => r.python)).sort(numeric),
    rows: [...rows.values()].filter((row) => row.cells.size > 0),
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
