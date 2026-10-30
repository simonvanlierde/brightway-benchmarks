import { readFile } from "node:fs/promises";
import { describe, expect, it } from "vitest";
import {
  type BenchmarkIndex,
  ContractError,
  checkReferences,
  folder,
  loadIndex,
  loadReport,
} from "../src/lib/contract";

const BASE = "https://data.test/ui/";
const FIXTURES = new URL("fixtures/data/", import.meta.url);

/** A fetch that serves test/fixtures/data/ at BASE, with OVERRIDES (path -> body) on top. */
function serve(overrides: Record<string, string> = {}): typeof fetch {
  return (async (input: string | URL | Request) => {
    const path = String(input).slice(BASE.length);
    const body = overrides[path] ?? (await readFile(new URL(path, FIXTURES), "utf8").catch(() => undefined));
    return body === undefined ? new Response("", { status: 404 }) : new Response(body);
  }) as typeof fetch;
}

async function fixture(path: string): Promise<Record<string, unknown>> {
  return JSON.parse(await readFile(new URL(path, FIXTURES), "utf8"));
}

describe("loadIndex", () => {
  it("reads the fixture index, which follows the schema", async () => {
    const index = await loadIndex(BASE, serve());
    expect(index.benchmarks.map((b) => b.name)).toEqual(["bench.Solve.time_solve"]);
    expect(index.commits.map((c) => c.release)).toEqual(["1.0", "1.1"]);
  });

  it("finds index.json under a base given without its trailing slash", async () => {
    await expect(loadIndex("https://data.test/ui", serve())).resolves.toBeTruthy();
  });

  it("refuses another format version by name, before the schema", async () => {
    const index = { ...(await fixture("index.json")), format_version: 2, cases: "changed" };
    await expect(loadIndex(BASE, serve({ "index.json": JSON.stringify(index) }))).rejects.toThrow(
      /format_version 2, this UI reads 1/,
    );
  });

  it("refuses an index that breaks the schema", async () => {
    const index = await fixture("index.json");
    delete index.cases;
    await expect(loadIndex(BASE, serve({ "index.json": JSON.stringify(index) }))).rejects.toThrow(/cases/);
  });

  it("refuses a report path that climbs out of the base", async () => {
    const index = await fixture("index.json");
    const [report] = index.reports as { path: string }[];
    if (report) report.path = "reports/../../secret.json";
    await expect(loadIndex(BASE, serve({ "index.json": JSON.stringify(index) }))).rejects.toThrow(ContractError);
  });

  it("names the URL when the fetch itself fails", async () => {
    const offline = (async () => {
      throw new TypeError("Failed to fetch");
    }) as typeof fetch;
    const failure = loadIndex(BASE, offline);
    await expect(failure).rejects.toThrow(ContractError);
    await expect(failure).rejects.toThrow(/data\.test\/ui\/index\.json: .*Failed to fetch/);
  });

  it("says which URL is missing", async () => {
    await expect(loadIndex("https://data.test/none/", serve())).rejects.toThrow(/none\/index\.json: HTTP 404/);
  });
  it("leaves out a report in a format this UI does not read", async () => {
    const index = await fixture("index.json");
    const reports = index.reports as { path: string; format: string }[];
    reports.push({ ...(reports[0] as { path: string; format: string }), path: "reports/new.json", format: "bmf/v1" });
    const loaded = await loadIndex(BASE, serve({ "index.json": JSON.stringify(index) }));
    expect(loaded.reports.map((r) => r.format)).toEqual(["bmf/v0", "bmf/v0"]);
  });
});

describe("loadReport", () => {
  it("reads every report the fixture index lists, each of which follows the schema", async () => {
    const index = await loadIndex(BASE, serve());
    const reports = await Promise.all(index.reports.map((r) => loadReport(BASE, r, serve())));
    const large = index.cases[1]?.id ?? "";
    expect(reports.map((r) => r[large]?.latency?.value)).toEqual([2e9, 1e9]);
  });

  it("refuses a report without a value", async () => {
    const index = await loadIndex(BASE, serve());
    const report = index.reports[0];
    if (!report) throw new Error("the fixture lists no report");
    const broken = serve({ [report.path]: JSON.stringify({ case: { latency: { lower_value: 1 } } }) });
    await expect(loadReport(BASE, report, broken)).rejects.toThrow(/value/);
  });
});

describe("folder", () => {
  it("resolves a relative base against the page", () => {
    expect(String(folder("data", "https://site.test/bench/index.html"))).toBe("https://site.test/bench/data/");
  });
});

describe("checkReferences", () => {
  it("passes the fixture index", async () => {
    const index = await loadIndex(BASE, serve());
    expect(() => checkReferences(index)).not.toThrow();
  });

  it("names an id that a record points at but the index does not define", async () => {
    const index = (await fixture("index.json")) as unknown as BenchmarkIndex;
    const [first] = index.cases;
    if (first) first.benchmark = "gone";
    expect(() => checkReferences(index)).toThrow(/cases\[0\]\.benchmark: no benchmarks entry "gone"/);
    await expect(loadIndex(BASE, serve({ "index.json": JSON.stringify(index) }))).rejects.toThrow(ContractError);
  });

  it("checks every kind of reference", async () => {
    const breaks: [string, (i: BenchmarkIndex) => void][] = [
      [
        "benchmarks[0].measures[0]",
        (i) => {
          if (i.benchmarks[0]) i.benchmarks[0].measures = ["gone"];
        },
      ],
      [
        "benchmarks[0].group",
        (i) => {
          if (i.benchmarks[0]) i.benchmarks[0].group = "gone";
        },
      ],
      [
        "environments[0].group",
        (i) => {
          if (i.environments[0]) i.environments[0].group = "gone";
        },
      ],
      [
        "cases[0].environment",
        (i) => {
          if (i.cases[0]) i.cases[0].environment = "gone";
        },
      ],
      [
        "commits[0].group",
        (i) => {
          if (i.commits[0]) i.commits[0].group = "gone";
        },
      ],
      [
        "reports[0].machine",
        (i) => {
          if (i.reports[0]) i.reports[0].machine = "gone";
        },
      ],
      [
        "reports[0].commit",
        (i) => {
          if (i.reports[0]) i.reports[0].commit = "gone";
        },
      ],
    ];
    for (const [where, edit] of breaks) {
      const index = (await fixture("index.json")) as unknown as BenchmarkIndex;
      edit(index);
      expect(() => checkReferences(index), where).toThrow(`${where}:`);
    }
  });
});
