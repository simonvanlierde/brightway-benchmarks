import { readFile } from "node:fs/promises";
import { describe, expect, it } from "vitest";
import type { BenchmarkIndex, BenchmarkReport } from "../src/lib/contract";
import type { LatestChange } from "../src/lib/history";
import {
  benchLabel,
  benchmarkLabel,
  breakable,
  changesFor,
  displayNames,
  findBench,
  format,
  latestChanges,
  lines,
  pageOf,
  percent,
  percentRange,
  pickParams,
  pText,
  readView,
  seriesOf,
  seriesSlots,
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
    const view = {
      bench: "b-1",
      params: ["ecoinvent", "a, b&c"],
      measure: "latency",
      machine: "m",
      group: "g",
      direction: "worse",
      q: "multi lca & é",
    };
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
    expect(ticksFor(steps, 5)).toEqual(["1.0", "1.1", "1.2", "1.3", "1.4"]);
    // With room for every step, a commit that is not a release keeps its label too.
    expect(ticksFor(steps, 20)).toEqual(steps.map((s) => s.label));
    expect(ticksFor([{ label: "aaaa1111", released: false }], 3)).toEqual(["aaaa1111"]);
  });
});

describe("seriesSlots", () => {
  const index = {
    environments: [
      { id: "a", label: "KLU" },
      { id: "b", label: "PyPardiso" },
      { id: "c", label: "SuperLU" },
      { id: "d", label: "PyPardiso" },
      { id: "e" },
    ],
  } as unknown as BenchmarkIndex;
  const line = (env: string) => ({ env }) as Parameters<typeof seriesSlots>[1][number];
  it("gives a label the same colour on every chart, from its place among all labels", () => {
    expect(seriesSlots(index, [line("b"), line("c")])).toEqual([1, 2]);
    expect(seriesSlots(index, [line("c")])).toEqual([2]);
    // Another group's environment with the same label takes the same colour.
    expect(seriesSlots(index, [line("a"), line("d")])).toEqual([0, 1]);
  });
  it("falls back to the line's place when a line has no label or two lines would share a colour", () => {
    expect(seriesSlots(index, [line("c"), line("e")])).toEqual([0, 1]);
    expect(seriesSlots(index, [line("b"), line("d")])).toEqual([0, 1]);
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

  it("shows one benchmark's changes as a range from the smallest to the largest", () => {
    const rows = [0.2, 0.21].map((ratio) => ({ change: { ratio } }) as LatestChange);
    expect(percentRange(rows)).toBe("−79% to −80%");
    expect(percentRange(rows.slice(0, 1))).toBe("−80%");
    expect(percentRange([])).toBe("");
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

describe("readable benchmark names", () => {
  it("keeps activity context and distinguishes memory from time", () => {
    expect(benchmarkLabel("bench_lca.MultiScores.time_scores")).toBe("Multi Scores");
    expect(benchmarkLabel("bench_import.timeraw_import_bw2calc")).toBe("Import bw2calc");
    expect(benchmarkLabel("bench_write.DatabaseWrite.peakmem_write")).toBe("Database Write · Peak memory");
    expect(benchmarkLabel("plain")).toBe("Plain");
    // A word the class name already has is not said twice.
    expect(benchmarkLabel("bench_lca.SingleScore.time_first_score")).toBe("First score");
    expect(benchmarkLabel("bench_lca.NewDemand.time_redo_lci")).toBe("New Demand · redo lci");
  });

  it("prefers the data's label, and adds the name when two in a group read the same", () => {
    const bench = (name: string, label?: string) =>
      ({
        id: name,
        group: "g",
        name,
        measures: ["t"],
        params: [],
        ...(label ? { label } : {}),
      }) as BenchmarkIndex["benchmarks"][number];
    const a = bench("m.A.time_x", "Same");
    const b = bench("m.B.time_y", "Same");
    const c = bench("m.C.time_z", "Own");
    const d = bench("m.D.time_w");
    const index = { benchmarks: [a, b, c, d] } as BenchmarkIndex;
    expect(benchLabel(index, a)).toBe("Same (m.A.time_x)");
    expect(benchLabel(index, c)).toBe("Own");
    expect(benchLabel(index, d)).toBe("D · w");
  });
});

describe("narrow chart ticks", () => {
  it("keeps both endpoints without exceeding the tick budget", () => {
    const steps = Array.from({ length: 15 }, (_, i) => ({ label: `1.${i}`, released: true }));
    expect(ticksFor(steps, 3)).toEqual(["1.0", "1.7", "1.14"]);
  });
});

describe("primary navigation state", () => {
  it("preserves the page, platform, Python and selected check in a shared link", () => {
    const view = { params: [], page: "compatibility", platform: "linux", python: "3.12", check: "linux-312-latest" };
    expect(readView(writeView(view))).toEqual(view);
  });
});

describe("page routing", () => {
  it("keeps legacy histories, overview filters and the compatibility anchor", () => {
    expect(pageOf({ params: [], bench: "known-bench" })).toBe("explorer");
    expect(pageOf({ params: [], direction: "worse" })).toBe("explorer");
    expect(pageOf({ params: [], page: "home" })).toBe("home");
    expect(pageOf({ params: [], page: "unknown" })).toBe("home");
    // Compatibility is part of Setup now, and release changes open the Benchmarks overview.
    expect(pageOf(readView("", "#works-together"))).toBe("home");
    expect(readView("", "#works-together").page).toBe("compatibility");
    expect(pageOf(readView("?page=changes", "#works-together"))).toBe("explorer");
    expect(pageOf(readView("", "#latest-release"))).toBe("explorer");
  });

  it("finds a benchmark by id, or by name in a named group as the old asv links give it", () => {
    const index = {
      groups: [
        { id: "a-1", name: "a" },
        { id: "b-1", name: "b" },
      ],
      benchmarks: [
        { id: "a-x", group: "a-1", name: "x" },
        { id: "b-x", group: "b-1", name: "x" },
      ],
    } as unknown as BenchmarkIndex;
    expect(findBench(index, { params: [], bench: "b-x" })?.id).toBe("b-x");
    expect(findBench(index, { params: [], bench: "x", group: "b" })?.id).toBe("b-x");
    expect(findBench(index, { params: [], bench: "x" })?.id).toBe("a-x");
    expect(findBench(index, { params: [], bench: "y", group: "b" })).toBeUndefined();
  });

  it("reads one case's series in its group commit order", () => {
    const index = {
      commits: [
        { id: "c1", group: "g", date: "2026-01-01T00:00:00Z", release: "1.0" },
        { id: "c2", group: "g", date: "2026-02-01T00:00:00Z" },
        { id: "c3", group: "g", date: "2026-03-01T00:00:00Z", release: "1.1" },
        { id: "c1", group: "other", date: "2026-01-01T00:00:00Z", release: "1.0" },
        { id: "c3", group: "other", date: "2026-03-01T00:00:00Z", release: "1.1" },
      ],
    } as unknown as BenchmarkIndex;
    const reports = new Map([
      ["c3", { k: { latency: { value: 3 } } }],
      ["c1", { k: { latency: { value: 1 } } }],
      ["c2", { other: { latency: { value: 9 } } }],
    ]);
    expect(seriesOf(index, reports, "k", "latency", "g")).toEqual([
      { commit: "c1", value: 1, released: true },
      { commit: "c3", value: 3, released: true },
    ]);
  });
});

describe("links already posted", () => {
  it("p=ecoinvent still selects the ecoinvent size", async () => {
    const index = JSON.parse(
      await readFile(new URL("fixtures/real/index.json", import.meta.url), "utf8"),
    ) as BenchmarkIndex;
    const bench = index.benchmarks.find((b) =>
      b.params.some((a) => a.name === "size" && a.values.includes("'ecoinvent'") && a.values[0] !== "'ecoinvent'"),
    );
    if (!bench) throw new Error("the fixture has no benchmark where ecoinvent is not the first size");
    const at = bench.params.findIndex((a) => a.name === "size");
    const wanted = bench.params.map((a, i) => (i === at ? "ecoinvent" : ((a.labels ?? a.values)[0] ?? "")));
    expect(pickParams(bench, wanted)[at]).toBe("'ecoinvent'");
  });
});

describe("the noise band", () => {
  it("falls back to the floor without a usable spread", () => {
    const index = {
      measures: [{ id: "latency", name: "Time", unit: "ns", noise: { floor: 0.02, spreads: 3 } }],
      environments: [{ id: "e", group: "g", name: "e" }],
      cases: [{ id: "k", benchmark: "b", environment: "e", params: [] }],
      commits: ["c1", "c2", "c3"].map((id) => ({ id, group: "g", date: "2026-01-01T00:00:00Z" })),
    } as unknown as BenchmarkIndex;
    const reports = new Map<string, BenchmarkReport>([
      ["c1", { k: { latency: { value: 0, lower_value: 0, upper_value: 0 } } }],
      ["c2", { k: { latency: { value: 2 } } }],
      ["c3", { k: { latency: { value: 2, lower_value: 1, upper_value: Number.NaN } } }],
    ]);
    const bench = { id: "b", group: "g", params: [] } as unknown as Parameters<typeof lines>[1];
    expect(lines(index, bench, [], "latency", reports)[0]?.points.map((p) => p.noise)).toEqual([0.02, 0.02, 0.02]);
  });

  it("is the rule the exporter's release changes use", async () => {
    const real = new URL("fixtures/real/", import.meta.url);
    const read = async <T>(path: string): Promise<T> => JSON.parse(await readFile(new URL(path, real), "utf8"));
    const index = await read<BenchmarkIndex>("index.json");
    const found = new Set(
      (index.changes ?? []).filter((c) => c.method === "release").map((c) => `${c.case}/${c.baseline}/${c.commit}`),
    );
    let pairs = 0;
    for (const bench of index.benchmarks.filter((b) => b.measures.includes("latency"))) {
      const reports = new Map<string, BenchmarkReport>();
      for (const r of index.reports.filter((r) => r.group === bench.group)) {
        reports.set(r.commit, await read<BenchmarkReport>(r.path));
      }
      for (const c of index.cases.filter((c) => c.benchmark === bench.id)) {
        for (const line of lines(index, bench, c.params, "latency", reports).filter((l) => l.case === c.id)) {
          const kept = line.points.filter((p) => p.released);
          for (const [i, b] of kept.slice(1).entries()) {
            const a = kept[i];
            if (!a || a.noise === undefined || b.noise === undefined) throw new Error("a point without its band");
            // A release counts as a change once it moves beyond the wider of the two bands.
            expect(Math.abs(b.value / a.value - 1) > Math.max(a.noise, b.noise)).toBe(
              found.has(`${c.id}/${a.commit}/${b.commit}`),
            );
            pairs++;
          }
        }
      }
    }
    expect(pairs).toBeGreaterThan(700);
  });
});
