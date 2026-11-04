import { expect, it } from "vitest";
import { readView } from "../src/lib/history";
import { viewerHref } from "../src/lib/story-links";

it("builds a link the viewer reads back as the same view", () => {
  const href = viewerHref("/brightway-benchmarks/", "bw2calc-conda", "bench_lca.MultiScores.time_scores", [
    "ecoinvent",
    "30",
    "MultiLCA",
  ]);
  expect(href.startsWith("/brightway-benchmarks/?")).toBe(true);
  expect(readView(href.slice(href.indexOf("?")))).toEqual({
    page: "explorer",
    group: "bw2calc-conda",
    bench: "bench_lca.MultiScores.time_scores",
    params: ["ecoinvent", "30", "MultiLCA"],
  });
});
