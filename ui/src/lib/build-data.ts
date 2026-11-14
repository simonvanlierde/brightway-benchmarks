// Build time only, for the pages Astro renders: the data the site will serve, read from disk.
// UI_DATA_DIR names its folder (the site workflow exports the data before it builds). Without it, a
// build that serves the test fixtures (no PUBLIC_DATA_URL: the browser tests and `just ui-serve`)
// reads them; any other build cannot know the data, and these answer as if it had everything.
import { existsSync, readFileSync } from "node:fs";
import type { BenchmarkIndex, Guidance } from "./contract";

const dir = process.env.UI_DATA_DIR ?? (import.meta.env.PUBLIC_DATA_URL ? undefined : "test/fixtures/real");
const index: Pick<BenchmarkIndex, "groups" | "benchmarks"> | undefined = dir
  ? JSON.parse(readFileSync(`${dir}/index.json`, "utf8"))
  : undefined;

/** Whether BENCH (a benchmark's name) is published in GROUP (a group's name or id), so a page may link its history. */
export function published(group: string, bench: string): boolean {
  if (!index) return true;
  const ids = new Set(index.groups.filter((g) => g.name === group || g.id === group).map((g) => g.id));
  return index.benchmarks.some((b) => ids.has(b.group) && b.name === bench);
}

/** Setup's title and intro from guidance.json, so the page can draw them before its script runs; unchecked, as the viewer redraws them from the checked file. */
export function setupIntro(): Pick<Guidance, "title" | "intro"> | undefined {
  const path = `${dir}/guidance.json`;
  if (!dir || !existsSync(path)) return undefined;
  const { title, intro } = JSON.parse(readFileSync(path, "utf8")) as Partial<Guidance>;
  return typeof title === "string" && typeof intro === "string" ? { title, intro } : undefined;
}
