/** Rows of end-of-line labels, top to bottom: pushed apart by `gap`, then kept at or above `floor` (the plot's bottom). */
export function spreadLabels(ys: readonly number[], floor: number, gap = 14): number[] {
  const out = [...ys];
  let prev = Number.NEGATIVE_INFINITY;
  for (const [i, y] of out.entries()) {
    out[i] = Math.max(y, prev + gap);
    prev = out[i] ?? prev;
  }
  let next = floor;
  for (let i = out.length - 1; i >= 0; i--) {
    out[i] = Math.min(out[i] ?? next, next);
    next = (out[i] ?? next) - gap;
  }
  return out;
}
