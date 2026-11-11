import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import type { BenchmarkIndex } from "../src/lib/contract";
import { seriesSlots } from "../src/lib/history";
import { SERIES } from "../src/lib/story-series";

const index: BenchmarkIndex = JSON.parse(readFileSync(new URL("./fixtures/real/index.json", import.meta.url), "utf8"));

describe("the stories' solver colours", () => {
  it("are the colours the viewer's charts give the same environments", () => {
    const slot = (label: string) => {
      const env = index.environments.find((e) => e.label === label);
      return (seriesSlots(index, [{ env: env?.id ?? "" }])[0] ?? -1) + 1;
    };
    expect(SERIES).toEqual({ umfpack: slot("UMFPACK"), pypardiso: slot("PyPardiso, MKL"), superlu: slot("SuperLU") });
  });
});
