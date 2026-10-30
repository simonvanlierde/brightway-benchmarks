import { readFile } from "node:fs/promises";
import { describe, expect, it } from "vitest";

// WCAG 2.2 AA asks 3:1 for the graphics that carry meaning (lines, symbols, control borders)
// against what they sit on. The colours are read from the stylesheet, so this follows edits.
const css = await readFile(new URL("../src/styles.css", import.meta.url), "utf8");

function tokens(block: string): Record<string, string> {
  return Object.fromEntries([...block.matchAll(/--([\w-]+):\s*(#[0-9a-f]{6})/gi)].map((m) => [m[1], m[2]]));
}

const light = tokens(css.slice(0, css.indexOf("@media")));
const dark = tokens(css.slice(css.indexOf("@media (prefers-color-scheme: dark)"), css.indexOf("* {")));

function luminance(hex: string): number {
  const [r, g, b] = [1, 3, 5].map((i) => {
    const c = Number.parseInt(hex.slice(i, i + 2), 16) / 255;
    return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * (r ?? 0) + 0.7152 * (g ?? 0) + 0.0722 * (b ?? 0);
}

function contrast(a: string, b: string): number {
  const [x, y] = [luminance(a), luminance(b)].sort((p, q) => q - p);
  return ((x ?? 0) + 0.05) / ((y ?? 0) + 0.05);
}

describe.each([
  ["light", light],
  ["dark", dark],
])("%s theme", (_, t) => {
  const series = Array.from({ length: 8 }, (__, i) => `s${i + 1}`);

  it.each([...series, "control", "worse", "better"])("--%s is at least 3:1 on the chart and the page", (name) => {
    for (const ground of ["surface", "page"]) {
      expect(contrast(t[name] ?? "", t[ground] ?? ""), `${name} on ${ground}`).toBeGreaterThanOrEqual(3);
    }
  });

  it("keeps text at 4.5:1", () => {
    for (const name of ["ink", "ink-2", "muted", "accent", "worse", "better"]) {
      expect(contrast(t[name] ?? "", t.surface ?? ""), name).toBeGreaterThanOrEqual(4.5);
    }
  });
});
