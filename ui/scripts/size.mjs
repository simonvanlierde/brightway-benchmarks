// Fails when what a page loads, gzipped, is over the budget. Run after `pnpm build`.
import { existsSync, readdirSync, readFileSync } from "node:fs";
import { join, relative } from "node:path";
import { fileURLToPath } from "node:url";
import { gzipSync } from "node:zlib";

// Observable Plot (with its d3 parts) is about 108 KB of it; the rest is Svelte and our code.
const VIEWER_BUDGET_KB = 182;
// /findings/ carries docs/findings.md in full, about 9 KB of it, and grows with each write-up.
const STATIC_BUDGET_KB = 28;
// The first search loads Pagefind's script, worker and WebAssembly (about 85 KB), its index and up to five
// pages' fragments, which grow with the static pages. Pagefind's own UI bundles are built beside them but never loaded.
const SEARCH_BUDGET_KB = 130;
const dist = fileURLToPath(new URL("../dist/", import.meta.url));
const name = (file) => relative(dist, file).replaceAll("\\", "/");

function files(dir) {
  return readdirSync(dir, { withFileTypes: true }).flatMap((e) =>
    e.isDirectory() ? (["data", "pagefind"].includes(e.name) ? [] : files(join(dir, e.name))) : [join(dir, e.name)],
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
const pagefind = join(dist, "pagefind");
if (existsSync(pagefind)) {
  const size = (file) => gzipSync(readFileSync(file)).length;
  const all = files(pagefind);
  const loaded = all.filter((f) =>
    /\/(pagefind\.js|pagefind-worker\.js|pagefind-entry\.json|wasm\.en\.pagefind|[^/]+\.pf_meta|index\/[^/]+)$/.test(f),
  );
  // Each result shown fetches its page's fragment; App.svelte shows at most five pages.
  const fragments = all
    .filter((f) => /\/fragment\/[^/]+$/.test(f))
    .map(size)
    .sort((a, b) => b - a)
    .slice(0, 5);
  const total = (loaded.reduce((sum, file) => sum + size(file), 0) + fragments.reduce((a, b) => a + b, 0)) / 1024;
  console.log(`size: first search ${total.toFixed(1)} KB gzipped, budget ${SEARCH_BUDGET_KB} KB`);
  failed ||= total > SEARCH_BUDGET_KB;
}
if (failed) process.exit(1);
