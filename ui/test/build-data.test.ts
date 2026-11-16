import { mkdirSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, expect, test, vi } from "vitest";

// build-data reads UI_DATA_DIR once, at import, so each case imports a fresh copy.
async function load(files: Record<string, unknown>) {
  const dir = mkdtempSync(join(tmpdir(), "build-data-"));
  mkdirSync(dir, { recursive: true });
  for (const [name, body] of Object.entries(files)) writeFileSync(join(dir, name), JSON.stringify(body));
  vi.stubEnv("UI_DATA_DIR", dir);
  vi.resetModules();
  return import("../src/lib/build-data");
}
afterEach(() => vi.unstubAllEnvs());

const index = {
  groups: [{ id: "g-1", name: "bw2calc" }],
  benchmarks: [
    { group: "g-1", name: "bench_lca.One" },
    { group: "other", name: "bench_lca.Two" },
  ],
};

test("published() accepts a group's name or id and refuses a benchmark of another group", async () => {
  const { published } = await load({ "index.json": index });
  expect(published("bw2calc", "bench_lca.One")).toBe(true);
  expect(published("g-1", "bench_lca.One")).toBe(true);
  expect(published("bw2calc", "bench_lca.Two")).toBe(false);
  expect(published("bw2calc", "bench_lca.Missing")).toBe(false);
});

test("setupIntro() reads title and intro, and answers nothing without a usable guidance.json", async () => {
  expect((await load({ "index.json": index, "guidance.json": { title: "T", intro: "I", x: 1 } })).setupIntro()).toEqual(
    {
      title: "T",
      intro: "I",
    },
  );
  expect((await load({ "index.json": index })).setupIntro()).toBeUndefined();
  expect((await load({ "index.json": index, "guidance.json": { title: "T" } })).setupIntro()).toBeUndefined();
});
