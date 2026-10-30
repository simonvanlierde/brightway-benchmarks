// The one module that knows the data's format: the rest of the UI imports its types from here.
import { Ajv2020, type ValidateFunction } from "ajv/dist/2020.js";
import indexSchema from "../../schema/index.schema.json" with { type: "json" };
import reportSchema from "../../schema/report.schema.json" with { type: "json" };
import type { BenchmarkIndex } from "./index.gen";
import type { BenchmarkReport } from "./report.gen";

export type { BenchmarkIndex, BenchmarkReport };
export type Report = BenchmarkIndex["reports"][number];

/** The index format this UI reads. */
export const FORMAT_VERSION = 1;
/** The report formats this UI reads. */
export const REPORT_FORMATS: readonly string[] = ["bmf/v0"];

// NOTE: formats (date-time, uri) are not checked here, to keep ajv-formats out of the page. The
// exporter's tests check date-time against the same schema.
const ajv = new Ajv2020({ allErrors: true, validateFormats: false });
const checkIndex = ajv.compile<BenchmarkIndex>(indexSchema);
const checkReport = ajv.compile<BenchmarkReport>(reportSchema);

/** The data is missing, or does not have the shape ui/schema/ gives. */
export class ContractError extends Error {
  override name = "ContractError";
}

/** BASE as a folder URL. A relative BASE resolves against the page, so it needs a browser or FROM. */
export function folder(base: string | URL, from: string | undefined = globalThis.location?.href): URL {
  const text = String(base);
  return new URL(text.endsWith("/") ? text : `${text}/`, from);
}

async function getJson(url: URL, fetcher: typeof fetch): Promise<unknown> {
  let response: Response;
  try {
    response = await fetcher(url);
  } catch (error) {
    throw new ContractError(`${url}: ${error}`, { cause: error });
  }
  if (!response.ok) throw new ContractError(`${url}: HTTP ${response.status}`);
  try {
    return await response.json();
  } catch (error) {
    throw new ContractError(`${url}: not JSON (${error})`);
  }
}

function valid<T>(check: ValidateFunction<T>, data: unknown, url: URL): T {
  if (check(data)) return data;
  throw new ContractError(`${url}: ${ajv.errorsText(check.errors)}`);
}

/** Throw a ContractError for an id a record points at that the index does not define. */
export function checkReferences(index: BenchmarkIndex): void {
  const ids = (records: { id: string }[]) => new Set(records.map((r) => r.id));
  const defined = {
    groups: ids(index.groups),
    measures: ids(index.measures),
    machines: ids(index.machines),
    environments: ids(index.environments),
    benchmarks: ids(index.benchmarks),
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
}

/** BASE/index.json, checked against the schema and for dangling ids. */
export async function loadIndex(base: string | URL, fetcher: typeof fetch = fetch): Promise<BenchmarkIndex> {
  const url = new URL("index.json", folder(base));
  const data = await getJson(url, fetcher);
  // Checked before the schema, so a newer file says so instead of failing on some field.
  const version = (data as { format_version?: unknown } | null)?.format_version;
  if (version !== FORMAT_VERSION) {
    throw new ContractError(`${url}: format_version ${version}, this UI reads ${FORMAT_VERSION}`);
  }
  const index = valid(checkIndex, data, url);
  checkReferences(index);
  return { ...index, reports: index.reports.filter((r) => REPORT_FORMATS.includes(r.format)) };
}

/** One report the index lists, from BASE (the folder that holds index.json), checked against the schema. */
export async function loadReport(
  base: string | URL,
  report: Report,
  fetcher: typeof fetch = fetch,
): Promise<BenchmarkReport> {
  const url = new URL(report.path, folder(base));
  return valid(checkReport, await getJson(url, fetcher), url);
}
