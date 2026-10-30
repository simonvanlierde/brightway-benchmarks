// Fails when what a page loads, gzipped, is over the budget. Run after `pnpm build`.
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { gzipSync } from "node:zlib";

// Observable Plot (with its d3 parts) is about 108 KB of it; the rest is Svelte, ajv and our code.
const BUDGET_KB = 170;
const dist = new URL("../dist/", import.meta.url).pathname;

function files(dir) {
  return readdirSync(dir, { withFileTypes: true }).flatMap((e) =>
    e.isDirectory() ? (e.name === "data" ? [] : files(join(dir, e.name))) : [join(dir, e.name)],
  );
}

const shipped = files(dist).filter((f) => /\.(js|css|html)$/.test(f));
const total = shipped.reduce((sum, f) => sum + gzipSync(readFileSync(f)).length, 0) / 1024;
console.log(`size: ${total.toFixed(1)} KB gzipped in ${shipped.length} files, budget ${BUDGET_KB} KB`);
if (total > BUDGET_KB) process.exit(1);
