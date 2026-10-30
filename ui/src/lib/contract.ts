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

// NOTE: formats (date-time, uri) are not checked, as in the Python tests' validator.
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
  const response = await fetcher(url);
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

/** BASE/index.json, checked against the schema. */
export async function loadIndex(base: string | URL, fetcher: typeof fetch = fetch): Promise<BenchmarkIndex> {
  const url = new URL("index.json", folder(base));
  const data = await getJson(url, fetcher);
  // Checked before the schema, so a newer file says so instead of failing on some field.
  const version = (data as { format_version?: unknown } | null)?.format_version;
  if (version !== FORMAT_VERSION) {
    throw new ContractError(`${url}: format_version ${version}, this UI reads ${FORMAT_VERSION}`);
  }
  return valid(checkIndex, data, url);
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
