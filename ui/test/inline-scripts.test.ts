import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test } from "vitest";
import { inlineScripts, policy } from "../astro.config.mjs";

test("inlineScripts lists the code that runs, not data or external scripts", () => {
  const html =
    '<script data-inline-ok>a()</script><script src="x.js"></script><script type="application/ld+json">{}</script><script>b()</script>';
  expect(inlineScripts(html)).toEqual([
    ["<script data-inline-ok>", "a()"],
    ["<script>", "b()"],
  ]);
});

// The build hook throws for an unmarked script; run it the way Astro does, on a built dir.
test("the build hook fails on an inline script without data-inline-ok", () => {
  const page = (script: string) =>
    `<html><head><meta charset="utf-8"><meta http-equiv="content-security-policy" content="script-src 'self'"></head><body>${script}</body></html>`;
  const run = (script: string) => {
    const dir = mkdtempSync(join(tmpdir(), "csp-"));
    writeFileSync(join(dir, "index.html"), page(script));
    policy.hooks["astro:build:done"]({ dir: new URL(`file://${dir}/`) });
  };
  expect(() => run("<script data-inline-ok>ok()</script>")).not.toThrow();
  expect(() => run("<script>evil()</script>")).toThrow(/data-inline-ok/);
});
