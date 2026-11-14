import { readFile } from "node:fs/promises";
import { describe, expect, it } from "vitest";
import { loadRatios, type Ratios } from "../src/lib/contract";

const BASE = "https://data.test/ui/";
const REAL = new URL("fixtures/real/ratios.json", import.meta.url);

function serve(body?: string): typeof fetch {
  return (async () => (body === undefined ? new Response("", { status: 404 }) : new Response(body))) as typeof fetch;
}

async function real(): Promise<Ratios> {
  return JSON.parse(await readFile(REAL, "utf8"));
}

describe("loadRatios", () => {
  it("reads the real export of one hosted run", async () => {
    const ratios = await loadRatios(BASE, serve(await readFile(REAL, "utf8")));
    expect(ratios?.machines.map((m) => m.os)).toEqual(["Linux", "macOS", "Windows"]);
    expect(ratios?.comparisons.map((c) => c.id)).toEqual([
      "solvers",
      "install-path",
      "python",
      "bw2calc-release",
      "bw2data-release",
    ]);
  });

  it("is optional: no file is no comparisons, not an error", async () => {
    await expect(loadRatios(BASE, serve())).resolves.toBeUndefined();
  });

  it("refuses another format version by name", async () => {
    const data = { ...(await real()), format_version: 2 };
    await expect(loadRatios(BASE, serve(JSON.stringify(data)))).rejects.toThrow(/format_version 2, this UI reads 1/);
  });

  it("refuses a row for a machine the file does not list", async () => {
    const data = await real();
    const row = data.comparisons[0]?.candidates[0]?.rows[0];
    if (row) row.machine = "hosted/Plan9";
    await expect(loadRatios(BASE, serve(JSON.stringify(data)))).rejects.toThrow(/no machine "hosted\/Plan9"/);
  });

  it("refuses a run link that is not https", async () => {
    const data = await real();
    const machine = data.machines[0];
    if (machine) machine.run = "javascript:alert(1)";
    await expect(loadRatios(BASE, serve(JSON.stringify(data)))).rejects.toThrow(/pattern/);
  });
});
