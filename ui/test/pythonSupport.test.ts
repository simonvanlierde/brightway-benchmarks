import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import type { Guidance } from "../src/lib/contract";
import { codeParts, listed, supportLead, supportTable, supportWord } from "../src/lib/pythonSupport";

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

  it("claims only what failed when two unrelated failures share a reason", () => {
    const fail = (python: string, platform: string, package_: string) => ({
      python,
      platform,
      package: package_,
      status: "fail" as const,
      reason: "ModuleNotFoundError: No module named 'x'",
      date: "2026-11-10",
      run: "https://example.test/runs/1",
    });
    const pair = {
      packages: ["brightway25", "bw_timex"],
      pythons: [
        { version: "3.14", endOfLife: false, platforms: ["linux", "macos"] },
        { version: "3.15", endOfLife: false, platforms: ["linux", "macos"] },
      ],
      results: [fail("3.14", "linux", "brightway25"), fail("3.15", "macos", "bw_timex")],
    };
    // Merging by reason alone would read as both packages on both Pythons and both systems.
    expect(supportTable(pair, false)?.failures).toEqual([
      { reason: pair.results[0]?.reason, pythons: ["3.14"], platforms: ["linux"], packages: ["brightway25"] },
      { reason: pair.results[0]?.reason, pythons: ["3.15"], platforms: ["macos"], packages: ["bw_timex"] },
    ]);
    // The same failure of one package on two Pythons and on the same systems is one line.
    pair.results.push(fail("3.15", "linux", "brightway25"));
    pair.results.push(fail("3.15", "macos", "brightway25"));
    pair.results.push(fail("3.14", "macos", "brightway25"));
    expect(supportTable(pair, false)?.failures[0]).toMatchObject({
      pythons: ["3.14", "3.15"],
      platforms: ["linux", "macos"],
      packages: ["brightway25"],
    });
  });

  it("keeps the whole grid when results are missing: a missing cell is empty, not a missing row or column", () => {
    const dropped = support.results.filter((r) => !(r.python === "3.12" && r.platform === "macos"));
    const table = supportTable({ ...support, results: dropped }, false);
    expect(table?.pythons).toEqual(["3.11", "3.12", "3.13", "3.14", "3.15"]);
    expect(table?.rows).toHaveLength(9);
    expect(table?.rows.find((r) => r.package === "bw_timex" && r.platform === "macos")?.cells.has("3.12")).toBe(false);
    const none = supportTable({ ...support, results: [] }, true);
    expect(none?.pythons).toEqual(["3.9", "3.10"]);
    expect(none?.rows).toHaveLength(3);
    expect(none?.checked).toBe("");
  });

  it("returns nothing when the data lists no Python in the half asked for", () => {
    expect(supportTable({ ...support, pythons: support.pythons.filter((p) => !p.endOfLife) }, true)).toBeUndefined();
  });
});

describe("supportLead", () => {
  it("names the Pythons that work everywhere and why the others fail, from the data", () => {
    const table = supportTable(support, false);
    expect(table && supportLead(table)).toBe(
      "3.11 to 3.14 work on every system. 3.15 does not install yet: a dependency (cachebox) fails to build.",
    );
  });
  it("points to the reasons when a Python fails only in part, or for another reason", () => {
    const results = support.results.map((r) =>
      r.python === "3.12" && r.package === "bw_timex" ? { ...r, status: "fail" as const, reason: "ImportError: x" } : r,
    );
    const table = supportTable({ ...support, results }, false);
    expect(table && supportLead(table)).toBe(
      "3.11, 3.13 and 3.14 work on every system. 3.12 fails for 3 of 9 packages and systems; the reasons are below the table. 3.15 does not install yet: a dependency (cachebox) fails to build.",
    );
  });
});

describe("the cells and the reasons", () => {
  it("say Passed, as the check grid does", () => {
    expect(supportWord("pass")).toBe("Passed");
  });
  it("link the run of the oldest result once, beside its date", () => {
    expect(supportTable(support, false)?.run).toMatch(/actions\/runs\/\d+$/);
  });
  it("show a reason's backtick-quoted names as code, without the backticks", () => {
    expect(codeParts("Failed to build `cachebox==5.2.3`: error")).toEqual([
      { text: "Failed to build ", code: false },
      { text: "cachebox==5.2.3", code: true },
      { text: ": error", code: false },
    ]);
    expect(codeParts("plain")).toEqual([{ text: "plain", code: false }]);
  });
});

describe("listed", () => {
  it("joins with commas and an and", () => {
    expect(listed(["a"])).toBe("a");
    expect(listed(["a", "b", "c"])).toBe("a, b and c");
  });
});
