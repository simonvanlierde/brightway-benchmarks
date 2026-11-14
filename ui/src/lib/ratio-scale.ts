// Where a ratio sits on the comparison page's interval graphic: a log scale, so 2x faster and
// 2x slower are equal distances from 1.

interface Row {
  ratio: number | null;
  ci95: [number, number] | null;
}

/** A log scale from ROWS' intervals (and 1) to 0..100 percent, with its domain. */
export function ratioScale(rows: Row[]): ((x: number) => number) & { domain: [number, number] } {
  const ends = rows.flatMap((r) => r.ci95 ?? []);
  // At least 0.8 to 1.25, padded 10% beyond the widest interval.
  const lo = Math.log(Math.min(0.8, ...ends) / 1.1);
  const hi = Math.log(Math.max(1.25, ...ends) * 1.1);
  const scale = (x: number) => ((Math.log(x) - lo) / (hi - lo)) * 100;
  return Object.assign(scale, { domain: [Math.exp(lo), Math.exp(hi)] as [number, number] });
}
