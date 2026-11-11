import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import type { Guidance } from "../src/lib/contract";
import { listed, supportTable } from "../src/lib/pythonSupport";

// The exporter's output for the first python-probe run (see tests/test_export_guidance.py).
const guidance: Guidance = JSON.parse(readFileSync(new URL("./fixtures/real/guidance.json", import.meta.url), "utf8"));
const support = guidance.pythonSupport;
if (!support) throw new Error("the fixture has no pythonSupport");

describe("supportTable", () => {
  it("lists the supported Pythons on every system, apart from the end-of-life ones", () => {
    const table = supportTable(support, false);
    expect(table?.pythons).toEqual(["3.11", "3.12", "3.13", "3.14", "3.15"]);
    expect(table?.rows).toHaveLength(9); // three packages on three systems
  });

  it("lists the end-of-life Pythons for Linux only", () => {
    const table = supportTable(support, true);
    expect(table?.pythons).toEqual(["3.9", "3.10"]);
    expect(new Set(table?.rows.map((r) => r.platform))).toEqual(new Set(["linux"]));
  });

  it("keeps a failure and its reason, one entry for a reason shared by all three systems", () => {
    const [cachebox, ...others] = supportTable(support, false)?.failures ?? [];
    expect(others).toEqual([]);
    expect(cachebox?.reason).toContain("cachebox==5.2.3");
    expect(cachebox?.pythons).toEqual(["3.15"]);
    expect(cachebox?.platforms).toEqual(["linux", "macos", "windows"]);
    expect(cachebox?.packages).toEqual(["brightway25", "bw_graph_tools", "bw_timex"]);
  });

  it("returns nothing when no result falls in the half asked for", () => {
    expect(
      supportTable({ ...support, results: support.results.filter((r) => r.python !== "3.9") }, true)?.pythons,
    ).toEqual(["3.10"]);
    expect(supportTable({ ...support, results: [] }, true)).toBeUndefined();
  });
});

describe("listed", () => {
  it("joins with commas and an and", () => {
    expect(listed(["a"])).toBe("a");
    expect(listed(["a", "b", "c"])).toBe("a, b and c");
  });
});
