import { readFile } from "node:fs/promises";
import { describe, expect, it } from "vitest";
import type { BenchmarkIndex, BenchmarkReport } from "../src/lib/contract";
import {
  breakable,
  changesFor,
  displayNames,
  format,
  latestChanges,
  lines,
  percent,
  pickParams,
  pText,
  readView,
  shortNames,
  sig,
  ticksFor,
  verdict,
  writeView,
} from "../src/lib/history";

const FIXTURES = new URL("fixtures/data/", import.meta.url);
const json = async <T>(path: string): Promise<T> => JSON.parse(await readFile(new URL(path, FIXTURES), "utf8"));

async function fixture(): Promise<[BenchmarkIndex, Map<string, BenchmarkReport>]> {
  const index = await json<BenchmarkIndex>("index.json");
  const reports = new Map<string, BenchmarkReport>();
  for (const r of index.reports) reports.set(r.commit, await json<BenchmarkReport>(r.path));
  return [index, reports];
}

describe("the view in the URL", () => {
  it("survives a round trip, parameters in order", () => {
    const view = { bench: "b-1", params: ["ecoinvent", "a, b&c"], measure: "latency", machine: "m" };
    expect(readView(writeView(view))).toEqual(view);
  });

  it("is empty for the start page", () => {
    expect(writeView({ params: [] })).toBe("");
    expect(readView("")).toEqual({ params: [] });
  });

  it("falls back to each axis's first value for a label the benchmark lacks", async () => {
    const [index] = await fixture();
    const [bench] = index.benchmarks;
    if (!bench) throw new Error("no benchmark");
    expect(pickParams(bench, ["large"])).toEqual(["'large'"]);
    expect(pickParams(bench, ["gone"])).toEqual(["'small'"]);
    expect(pickParams(bench, [])).toEqual(["'small'"]);
  });
});

describe("shortNames", () => {
  it("keeps the words that tell environments apart", () => {
    const names = [
      "uv-py3.12-numpy2.5.3-pyklu0.2.0-scipy1.18.1-BWBENCH_SOLVERklu",
      "uv-py3.12-numpy2.5.3-pypardiso-scipy1.18.1",
      "uv-py3.12-numpy2.5.3-scipy1.18.1",
    ];
    expect(shortNames(names)).toEqual(["pyklu0.2.0 BWBENCH_SOLVERklu", "pypardiso", "default"]);
  });

  it("keeps a lone environment's whole name", () => {
    expect(shortNames(["py3.12"])).toEqual(["py3.12"]);
  });

  it("uses the data's labels when they tell every environment apart", () => {
    const envs = [
      { name: "uv-py3.12-pypardiso", label: "PyPardiso" },
      { name: "uv-py3.12", label: "SuperLU" },
    ];
    expect(displayNames(envs)).toEqual(["PyPardiso", "SuperLU"]);
    expect(displayNames([envs[0] ?? { name: "" }, { name: "uv-py3.12" }])).toEqual(["pypardiso", "default"]);
    expect(displayNames(envs.map((e) => ({ ...e, label: "same" })))).toEqual(["pypardiso", "default"]);
  });

  it("keeps whole names when the short ones would clash", () => {
    expect(shortNames(["a-b", "a-b-b"])).toEqual(["a-b", "a-b-b"]);
  });
});

describe("lines", () => {
  it("gives one line per environment, each point at its commit", async () => {
    const [index, reports] = await fixture();
    const [bench] = index.benchmarks;
    if (!bench) throw new Error("no benchmark");
    const [line] = lines(index, bench, ["'small'"], "latency", reports);
    expect(line?.short).toBe("py3.12");
    expect(line?.points.map((p) => [p.at, p.label, p.date, p.value, p.lower])).toEqual([
      [0, "1.0", "2026-01-01", 1e6, 0.99e6],
      [1, "1.1", "2026-02-01", 1e6, undefined],
    ]);
    expect(lines(index, bench, ["'small'"], "peak-memory", reports)).toEqual([]);
  });

  it("finds the changes on the lines shown", async () => {
    const [index, reports] = await fixture();
    const [bench] = index.benchmarks;
    if (!bench) throw new Error("no benchmark");
    const large = lines(index, bench, ["'large'"], "latency", reports);
    expect(changesFor(index, large, "latency", "box-0a1b2c3d4e5f").map((c) => c.ratio)).toEqual([0.5]);
    expect(changesFor(index, large, "latency", "other")).toEqual([]);
    expect(
      changesFor(index, lines(index, bench, ["'small'"], "latency", reports), "latency", "box-0a1b2c3d4e5f"),
    ).toEqual([]);
  });
});

describe("ticksFor", () => {
  it("prefers points with a release name, spread evenly, and keeps the last", () => {
    const steps = ["1.0", "aaaa1111", "1.1", "bbbb2222", "1.2", "1.3", "1.4"].map((label) => ({
      label,
      released: !/^[0-9a-f]{8}$/.test(label),
    }));
    expect(ticksFor(steps, 3)).toEqual(["1.0", "1.2", "1.4"]);
    expect(ticksFor(steps, 20)).toEqual(["1.0", "1.1", "1.2", "1.3", "1.4"]);
    expect(ticksFor([{ label: "aaaa1111", released: false }], 3)).toEqual(["aaaa1111"]);
  });
});

describe("breakable", () => {
  it("cuts after dots and underscores, losing nothing", () => {
    expect(breakable("bench_lca.MultiScores.time_scores")).toEqual([
      "bench_",
      "lca.",
      "MultiScores.",
      "time_",
      "scores",
    ]);
    expect(breakable("plain")).toEqual(["plain"]);
  });
});

describe("latestChanges", () => {
  it("lists the moves into each group's newest release", async () => {
    const [index] = await fixture();
    const [first, ...rest] = latestChanges(index);
    expect(rest).toEqual([]);
    expect(first?.way).toBe("better"); // 2 s to 1 s, and lower is better
    expect([first?.from, first?.to, first?.params, first?.env, first?.bench.name]).toEqual([
      "1.0",
      "1.1",
      ["large"],
      "py3.12",
      "bench.Solve.time_solve",
    ]);
  });
});

describe("numbers", () => {
  it("says which way a change went by the measure's direction", () => {
    expect(verdict(1.2, "lower")).toBe("worse");
    expect(verdict(0.8, "lower")).toBe("better");
    expect(verdict(1.2, "higher")).toBe("better");
    expect(verdict(1.2, undefined)).toBe("moved");
  });

  it("shows a tiny p-value as a bound, not as zero", () => {
    expect(pText(0)).toBe("p < 0.001");
    expect(pText(0.0123)).toBe("p = 0.012");
    expect(pText(undefined)).toBe("p unknown");
  });

  it("rounds percents to whole numbers from 2% up", () => {
    expect(percent(1.123)).toBe("+12%");
    expect(percent(0.916)).toBe("−8%");
    expect(percent(1.014)).toBe("+1.4%");
  });

  it("formats values to three significant figures in their own scale", () => {
    expect(format(1.234e9, "ns")).toBe("1.23 s");
    expect(format(45_600, "ns")).toBe("45.6 µs");
    expect(format(512, "ns")).toBe("512 ns");
    expect(format(7.5e8, "B")).toBe("750 MB");
    expect(format(3, "runs")).toBe("3.00 runs");
    expect(sig(1234.5)).toBe("1235");
    expect(sig(0.001234)).toBe("0.00123");
  });
});

describe("latestChanges order", () => {
  it("puts worse before better, then the larger move first", async () => {
    const [index] = await fixture();
    const [change] = index.changes ?? [];
    if (!change) throw new Error("no change");
    index.changes = [0.5, 1.1, 0.95, 1.4].map((ratio) => ({ ...change, ratio }));
    expect(latestChanges(index).map((r) => [r.way, r.change.ratio])).toEqual([
      ["worse", 1.4],
      ["worse", 1.1],
      ["better", 0.5],
      ["better", 0.95],
    ]);
  });
});
