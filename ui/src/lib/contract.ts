// The one module that knows the data's format: the rest of the UI imports its types from here.
import type { Guidance } from "./guidance.gen";
import type { BenchmarkIndex } from "./index.gen";
import type { RatioComparisons as Ratios } from "./ratios.gen";
import type { BenchmarkReport } from "./report.gen";
import { guidanceValidator, indexValidator, ratiosValidator, reportValidator, type Validator } from "./validators.gen";

export type { BenchmarkIndex, BenchmarkReport, Guidance, Ratios };
export type Report = BenchmarkIndex["reports"][number];
export type Change = NonNullable<BenchmarkIndex["changes"]>[number];

export const FORMAT_VERSION = 1;
/** guidance.json's own format: 2 gave each passing set one install command per package manager. */
export const GUIDANCE_VERSION = 2;
/** ratios.json's own format, from scripts/export_ratios.py. */
export const RATIOS_VERSION = 1;
export const REPORT_FORMATS: readonly string[] = ["bmf/v0"];

// The validators are compiled from ui/schema/ by `pnpm types` (scripts/generate-validators.mjs), so
// no schema is compiled in the browser. Formats go unchecked; the exporter's tests check date-time.

/** The data is missing, or does not have the shape ui/schema/ gives. */
export class ContractError extends Error {
  override name = "ContractError";
  /** missing: no file at the URL; version: a format this UI does not read; invalid: the wrong shape. */
  readonly kind: "missing" | "version" | "invalid";

  constructor(message: string, kind: ContractError["kind"] = "invalid", options?: ErrorOptions) {
    super(message, options);
    this.kind = kind;
  }
}

/** BASE as a folder URL. A relative BASE needs a page, or FROM, to resolve against. */
export function folder(base: string | URL, from: string | undefined = globalThis.location?.href): URL {
  const text = String(base);
  return new URL(text.endsWith("/") ? text : `${text}/`, from);
}

async function getJson(url: URL, fetcher: typeof fetch, optional = false): Promise<unknown> {
  let response: Response;
  try {
    response = await fetcher(url);
  } catch (error) {
    throw new ContractError(`${url}: ${error}`, "missing", { cause: error });
  }
  if (optional && response.status === 404) return undefined;
  if (!response.ok) throw new ContractError(`${url}: HTTP ${response.status}`, "missing");
  try {
    return await response.json();
  } catch (error) {
    throw new ContractError(`${url}: not JSON (${error})`);
  }
}

function valid<T>(check: Validator, data: unknown, url: URL): T {
  if (check(data)) return data as T;
  const errors = check.errors?.map((e) => `data${e.instancePath} ${e.message}`).join(", ") || "No errors";
  throw new ContractError(`${url}: ${errors}`);
}

/** Throw when a record names an id the index does not define. */
export function checkReferences(index: BenchmarkIndex): void {
  const ids = (records: { id: string }[]) => new Set(records.map((r) => r.id));
  const defined = {
    groups: ids(index.groups),
    measures: ids(index.measures),
    machines: ids(index.machines),
    environments: ids(index.environments),
    benchmarks: ids(index.benchmarks),
    cases: ids(index.cases),
    commits: new Set(index.commits.map((c) => `${c.group}/${c.id}`)),
  };
  const need = (kind: keyof typeof defined, id: string, where: string) => {
    if (!defined[kind].has(id)) throw new ContractError(`${where}: no ${kind} entry "${id}"`);
  };
  index.environments.forEach((e, i) => {
    need("groups", e.group, `environments[${i}].group`);
  });
  index.benchmarks.forEach((b, i) => {
    need("groups", b.group, `benchmarks[${i}].group`);
    b.measures.forEach((m, j) => {
      need("measures", m, `benchmarks[${i}].measures[${j}]`);
    });
  });
  index.cases.forEach((c, i) => {
    need("benchmarks", c.benchmark, `cases[${i}].benchmark`);
    need("environments", c.environment, `cases[${i}].environment`);
  });
  index.commits.forEach((c, i) => {
    need("groups", c.group, `commits[${i}].group`);
  });
  index.reports.forEach((r, i) => {
    need("groups", r.group, `reports[${i}].group`);
    need("machines", r.machine, `reports[${i}].machine`);
    need("commits", `${r.group}/${r.commit}`, `reports[${i}].commit`);
  });
  const caseGroup = new Map(index.cases.map((c) => [c.id, index.benchmarks.find((b) => b.id === c.benchmark)?.group]));
  index.changes?.forEach((c, i) => {
    need("cases", c.case, `changes[${i}].case`);
    need("machines", c.machine, `changes[${i}].machine`);
    need("measures", c.measure, `changes[${i}].measure`);
    need("commits", `${caseGroup.get(c.case)}/${c.commit}`, `changes[${i}].commit`);
    need("commits", `${caseGroup.get(c.case)}/${c.baseline}`, `changes[${i}].baseline`);
  });
}

/** BASE/index.json, checked against the schema and for dangling ids. */
export async function loadIndex(base: string | URL, fetcher: typeof fetch = fetch): Promise<BenchmarkIndex> {
  const url = new URL("index.json", folder(base));
  const data = await getJson(url, fetcher);
  // Checked before the schema, so a newer file says so instead of failing on some field.
  const version = (data as { format_version?: unknown } | null)?.format_version;
  if (version !== FORMAT_VERSION) {
    throw new ContractError(`${url}: format_version ${version}, this UI reads ${FORMAT_VERSION}`, "version");
  }
  const index = valid<BenchmarkIndex>(indexValidator, data, url);
  checkReferences(index);
  return { ...index, reports: index.reports.filter((r) => REPORT_FORMATS.includes(r.format)) };
}

/** One report the index lists, from BASE, checked against the schema. */
export async function loadReport(
  base: string | URL,
  report: Report,
  fetcher: typeof fetch = fetch,
): Promise<BenchmarkReport> {
  const url = new URL(report.path, folder(base));
  return valid<BenchmarkReport>(reportValidator, await getJson(url, fetcher), url);
}

/** Optional setup guidance beside index.json; a missing file leaves the benchmark viewer usable. */
export async function loadGuidance(base: string | URL, fetcher: typeof fetch = fetch): Promise<Guidance | undefined> {
  const url = new URL("guidance.json", folder(base));
  const data = await getJson(url, fetcher, true);
  if (data === undefined) return undefined;
  const version = (data as { format_version?: unknown } | null)?.format_version;
  if (version !== GUIDANCE_VERSION) {
    throw new ContractError(`${url}: format_version ${version}, this UI reads ${GUIDANCE_VERSION}`, "version");
  }
  const guidance = valid<Guidance>(guidanceValidator, data, url);
  const platforms = new Set(guidance.platforms.map((p) => p.id));
  const checks = new Map(guidance.checks.map((c) => [c.id, c]));
  if (platforms.size !== guidance.platforms.length || checks.size !== guidance.checks.length) {
    throw new ContractError(`${url}: duplicate platform or check id`);
  }
  for (const check of guidance.checks) {
    if (!platforms.has(check.platform)) throw new ContractError(`${url}: unknown platform ${check.platform}`);
  }
  for (const platform of guidance.platforms) {
    if (platform.defaultCheck && checks.get(platform.defaultCheck)?.platform !== platform.id) {
      throw new ContractError(`${url}: invalid defaultCheck for ${platform.id}`);
    }
  }
  return guidance;
}

/** Optional ratios across machines beside index.json; without the file the comparison page says none are published. */
export async function loadRatios(base: string | URL, fetcher: typeof fetch = fetch): Promise<Ratios | undefined> {
  const url = new URL("ratios.json", folder(base));
  const data = await getJson(url, fetcher, true);
  if (data === undefined) return undefined;
  const version = (data as { format_version?: unknown } | null)?.format_version;
  if (version !== RATIOS_VERSION) {
    throw new ContractError(`${url}: format_version ${version}, this UI reads ${RATIOS_VERSION}`, "version");
  }
  const ratios = valid<Ratios>(ratiosValidator, data, url);
  const machines = new Set(ratios.machines.map((m) => m.id));
  for (const c of ratios.comparisons)
    for (const k of c.candidates)
      for (const r of k.rows)
        if (!machines.has(r.machine)) throw new ContractError(`${url}: ${c.id}/${k.name}: no machine "${r.machine}"`);
  return ratios;
}
