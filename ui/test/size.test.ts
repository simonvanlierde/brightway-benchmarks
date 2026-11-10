import { spawnSync } from "node:child_process";
import { randomBytes } from "node:crypto";
import { copyFileSync, mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, expect, it } from "vitest";

const temporary: string[] = [];
afterEach(() => {
  for (const dir of temporary.splice(0)) rmSync(dir, { recursive: true, force: true });
});

function fixture() {
  const dir = mkdtempSync(join(tmpdir(), "bwbench-size-"));
  temporary.push(dir);
  mkdirSync(join(dir, "scripts"));
  mkdirSync(join(dir, "dist/_astro"), { recursive: true });
  mkdirSync(join(dir, "dist/about"));
  copyFileSync(new URL("../scripts/size.mjs", import.meta.url), join(dir, "scripts/size.mjs"));
  return dir;
}

const content = (kb: number) => randomBytes(kb * 1024).toString("base64");
const run = (dir: string) =>
  spawnSync(process.execPath, [join(dir, "scripts/size.mjs")], { cwd: dir, encoding: "utf8" });

it("budgets the viewer and a static About page separately", () => {
  const dir = fixture();
  writeFileSync(
    join(dir, "dist/index.html"),
    '<link rel="stylesheet" href="/brightway-benchmarks/ui/_astro/viewer.css"><script src="/_astro/app.js"></script>',
  );
  writeFileSync(join(dir, "dist/_astro/viewer.css"), "body { color: navy; }");
  writeFileSync(join(dir, "dist/_astro/app.js"), `const data = "${content(170)}";`);
  writeFileSync(join(dir, "dist/about/index.html"), `<main>${content(10)}</main>`);
  const result = run(dir);
  expect(result.status, result.stdout + result.stderr).toBe(0);
  expect(result.stdout).toContain("index.html");
  expect(result.stdout).toContain("about/index.html");
});

it("includes lazy JavaScript chunks in the viewer budget", () => {
  const dir = fixture();
  writeFileSync(join(dir, "dist/index.html"), '<script src="/_astro/app.js"></script>');
  writeFileSync(join(dir, "dist/_astro/app.js"), `const data = "${content(100)}";`);
  writeFileSync(join(dir, "dist/_astro/lazy-chart.js"), `const data = "${content(100)}";`);
  writeFileSync(join(dir, "dist/about/index.html"), "<main>About</main>");
  const result = run(dir);
  expect(result.status, result.stdout + result.stderr).toBe(1);
  expect(result.stdout).toMatch(/index.html \d+\.\d KB gzipped, budget 182 KB/);
});

it("fails when a static page itself exceeds the budget", () => {
  const dir = fixture();
  writeFileSync(join(dir, "dist/index.html"), "<main>Viewer</main>");
  writeFileSync(join(dir, "dist/about/index.html"), `<main>${content(21)}</main>`);
  const result = run(dir);
  expect(result.status, result.stdout + result.stderr).toBe(1);
  expect(result.stdout).toMatch(/about\/index.html \d+\.\d KB gzipped, budget 20 KB/);
});

it("counts a linked stylesheet toward a static page's budget", () => {
  const dir = fixture();
  writeFileSync(join(dir, "dist/index.html"), "<main>Viewer</main>");
  writeFileSync(
    join(dir, "dist/about/index.html"),
    '<link rel="stylesheet" href="/_astro/about.css"><main>About</main>',
  );
  writeFileSync(join(dir, "dist/_astro/about.css"), `body::after { content: "${content(21)}"; }`);
  const result = run(dir);
  expect(result.status, result.stdout + result.stderr).toBe(1);
  expect(result.stdout).toMatch(/about\/index.html \d+\.\d KB gzipped, budget 20 KB/);
});

it("keeps an inline theme script within the static-page budget", () => {
  const dir = fixture();
  writeFileSync(join(dir, "dist/index.html"), '<astro-island component-url="/_astro/app.js"></astro-island>');
  writeFileSync(join(dir, "dist/_astro/app.js"), `const data = "${content(170)}";`);
  writeFileSync(
    join(dir, "dist/about/index.html"),
    '<script>document.documentElement.dataset.theme = "light";</script><main>About</main>',
  );
  const result = run(dir);
  expect(result.status, result.stdout + result.stderr).toBe(0);
  expect(result.stdout).toMatch(/about\/index.html .*budget 20 KB/);
  expect(result.stdout).toMatch(/index.html 17\d\.\d KB gzipped, budget 182 KB/);
});
