<script lang="ts">
// A case's history beside its change, so a step reads apart from a trend; the number beside it carries
// the meaning, so the line stays hidden from screen readers.
let { points, mark }: { points: { commit: string; value: number }[]; mark: string } = $props();
const W = 96;
const H = 24;
const path = $derived.by(() => {
  if (points.length < 2) return { d: "", dot: undefined };
  const values = points.map((p) => p.value);
  const lo = Math.min(...values);
  const span = Math.max(...values) - lo || 1;
  const xy = points.map((p, i) => [(i / (points.length - 1)) * (W - 4) + 2, H - 2 - ((p.value - lo) / span) * (H - 4)]);
  const at = points.findIndex((p) => p.commit === mark);
  return { d: `M${xy.map(([x, y]) => `${x?.toFixed(1)},${y?.toFixed(1)}`).join("L")}`, dot: xy[at] };
});
</script>

{#if path.d}
  <svg class="sparkline" width={W} height={H} viewBox="0 0 {W} {H}" aria-hidden="true" focusable="false">
    <path d={path.d} />
    {#if path.dot}<circle cx={path.dot[0]} cy={path.dot[1]} r="2.5" />{/if}
  </svg>
{/if}
