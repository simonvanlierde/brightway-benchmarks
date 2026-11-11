import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import type { BenchmarkIndex } from "../src/lib/contract";
import { seriesSlots } from "../src/lib/history";
import { SERIES } from "../src/lib/story-series";

const index: BenchmarkIndex = JSON.parse(readFileSync(new URL("./fixtures/real/index.json", import.meta.url), "utf8"));

// The first-score charts the solver story links to: the pip one and the conda-forge one.
const CHARTS = {
  pip: "bw2calc-bench-lca-singlescore-time-first-score-0523b3edee8d",
  conda: "bw2calc-conda-bench-lca-singlescore-time-first-scor-7266cbe9fcd4",
};

describe("the stories' solver colours", () => {
  it.each(Object.entries(CHARTS))("are the colours the viewer's %s chart gives the same solvers", (_, bench) => {
    const shown = index.cases
      .filter((c) => c.benchmark === bench && c.params.join() === "'ecoinvent','LCA'")
      .map((c) => ({ env: c.environment }));
    const slots = seriesSlots(index, shown);
    const slot = (label: string) => {
      const at = shown.findIndex((l) => index.environments.find((e) => e.id === l.env)?.label === label);
      return at < 0 ? undefined : (slots[at] ?? -1) + 1;
    };
    expect(SERIES).toEqual({ umfpack: slot("UMFPACK"), pypardiso: slot("PyPardiso"), superlu: slot("SuperLU") });
  });
});
