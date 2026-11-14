import { describe, expect, it } from "vitest";
import { ratioScale } from "../src/lib/ratio-scale";

const row = (ratio: number | null, lo?: number, hi?: number) => ({
  ratio,
  ci95: ratio === null ? null : ([lo ?? ratio, hi ?? ratio] as [number, number]),
});

describe("ratioScale", () => {
  it("puts 1 inside the domain and each row on a log scale", () => {
    const x = ratioScale([row(1.2, 1.1, 1.3), row(0.5, 0.4, 0.6)]);
    expect(x.domain[0]).toBeLessThan(0.4);
    expect(x.domain[1]).toBeGreaterThan(1.3);
    // Equal factors either side of 1 are equal distances on a log scale.
    expect(x(2) - x(1)).toBeCloseTo(x(1) - x(0.5), 9);
    expect(x(x.domain[0])).toBe(0);
    expect(x(x.domain[1])).toBeCloseTo(100, 9);
  });

  it("keeps at least 0.8 to 1.25, so a narrow interval near 1 does not fill the track", () => {
    const x = ratioScale([row(1.01, 1.0, 1.02)]);
    expect(x.domain[0]).toBeLessThanOrEqual(0.8);
    expect(x.domain[1]).toBeGreaterThanOrEqual(1.25);
  });

  it("skips missing rows", () => {
    const x = ratioScale([row(null), row(20, 19, 21)]);
    expect(x.domain[1]).toBeGreaterThan(21);
    expect(x(1)).toBeGreaterThan(0);
  });
});
