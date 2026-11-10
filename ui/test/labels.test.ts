import { expect, it } from "vitest";
import { spreadLabels } from "../src/lib/labels";

it("keeps every label at or above the floor and a gap apart when the ends sit near the bottom", () => {
  const floor = 300;
  const ys = spreadLabels([290, 296, 301, 310], floor);
  for (const y of ys) expect(y).toBeLessThanOrEqual(floor);
  for (const [i, y] of ys.entries()) if (i) expect(y - (ys[i - 1] ?? 0)).toBeGreaterThanOrEqual(14);
  expect(ys.at(-1)).toBe(floor);
});

it("leaves well-spaced labels where they are", () => {
  expect(spreadLabels([10, 50, 90], 300)).toEqual([10, 50, 90]);
});
