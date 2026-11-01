// Fails when what a page loads, gzipped, is over the budget. Run after `pnpm build`.
import { readdirSync, readFileSync } from "node:fs";
import { join, relative } from "node:path";
import { fileURLToPath } from "node:url";
import { gzipSync } from "node:zlib";

// Observable Plot (with its d3 parts) is about 108 KB of it; the rest is Svelte, ajv and our code.
const VIEWER_BUDGET_KB = 180;
const STATIC_BUDGET_KB = 20;
const dist = fileURLToPath(new URL("../dist/", import.meta.url));
const name = (file) => relative(dist, file).replaceAll("\\", "/");

function files(dir) {
  return readdirSync(dir, { withFileTypes: true }).flatMap((e) =>
    e.isDirectory() ? (e.name === "data" ? [] : files(join(dir, e.name))) : [join(dir, e.name)],
  );
}

const shipped = files(dist).filter((f) => /\.(js|css|html)$/.test(f));
const sizes = new Map(shipped.map((file) => [file, gzipSync(readFileSync(file)).length]));
const scripts = shipped.filter((file) => file.endsWith(".js"));
const styles = shipped.filter((file) => file.endsWith(".css")).sort((a, b) => name(b).length - name(a).length);
let failed = false;
for (const page of shipped.filter((file) => file.endsWith(".html"))) {
  const html = readFileSync(page, "utf8");
  // Include lazy chart chunks for interactive pages; static pages do not load them.
  const interactive = /<astro-island\b|<script\b[^>]*\bsrc\s*=/i.test(html);
  const budget = interactive ? VIEWER_BUDGET_KB : STATIC_BUDGET_KB;
  const loaded = new Set([page, ...(interactive ? scripts : [])]);
  for (const [, href] of html.matchAll(/<link\b[^>]*\bhref\s*=\s*["']([^"']+)["'][^>]*>/gi)) {
    const path = decodeURIComponent(new URL(href, `https://build.invalid/${name(page)}`).pathname);
    if (!path.endsWith(".css")) continue;
    const style = styles.find((file) => path.endsWith(`/${name(file)}`));
    if (!style) throw new Error(`${name(page)} links a stylesheet absent from the build: ${href}`);
    loaded.add(style);
  }
  const total = [...loaded].reduce((sum, file) => sum + sizes.get(file), 0) / 1024;
  console.log(`size: ${name(page)} ${total.toFixed(1)} KB gzipped, budget ${budget} KB`);
  failed ||= total > budget;
}
if (failed) process.exit(1);
