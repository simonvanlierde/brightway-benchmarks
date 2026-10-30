<script lang="ts">
import * as Plot from "@observablehq/plot";
import type { Change } from "../lib/contract";
import { format, type Line, noiseText, percent, scaleFor, sig, ticksFor, verdict } from "../lib/history";

let {
  lines,
  changes,
  unit,
  better,
  title,
  filename,
}: {
  lines: Line[];
  changes: Change[];
  unit: string;
  better: "lower" | "higher" | undefined;
  title: string;
  filename: string;
} = $props();

const SYMBOLS = ["circle", "square", "triangle", "diamond", "star", "cross", "wye"];
const SLOTS = 8;

let width = $state(640);
let theme = $state(0); // bumped when the colour scheme changes, so the chart reads its colours again
let active = $state<number | null>(null); // the release the keyboard has selected, by position in `steps`
let host = $state<HTMLElement>();
let legend = $state<HTMLElement>();
let figure = $state<SVGSVGElement>();

$effect(() => {
  const media = matchMedia("(prefers-color-scheme: dark)");
  const bump = () => theme++;
  media.addEventListener("change", bump);
  return () => media.removeEventListener("change", bump);
});

const points = $derived(lines.flatMap((l) => l.points.map((p) => ({ ...p, short: l.short }))));
// One step per commit with a value on any line, in commit order: the x axis and the keyboard's stops.
const steps = $derived.by(() => {
  const by = new Map<number, typeof points>();
  for (const p of points) by.set(p.at, [...(by.get(p.at) ?? []), p]);
  return [...by.entries()].sort(([a], [b]) => a - b).map(([, ps]) => ps);
});
const scale = $derived.by(() => {
  const values = points.map((p) => p.value).sort((a, b) => a - b);
  return scaleFor(unit, values[Math.floor(values.length / 2)] ?? 1);
});
const changeAt = $derived.by(() => {
  const short = new Map(lines.map((l) => [l.case, l.short]));
  const out = new Map<string, { change: Change; short: string }[]>();
  for (const change of changes) {
    out.set(change.commit, [...(out.get(change.commit) ?? []), { change, short: short.get(change.case) ?? "" }]);
  }
  return out;
});

function words(change: Change): string {
  const way = verdict(change.ratio, better);
  if (change.method === "release") return `${percent(change.ratio)} ${way} (noise ${noiseText(change)})`;
  return `level shift ${percent(change.ratio)} ${way}`;
}

function describe(step: (typeof steps)[number]): string {
  const [first] = step;
  if (!first) return "";
  const rows = step.map((p) => `${p.short}: ${format(p.value, unit)}`);
  const marks = (changeAt.get(first.commit) ?? []).map((c) => `${c.short}: ${words(c.change)}`);
  return [`${first.label} · ${first.date}`, ...rows, ...marks].join("\n");
}

$effect(() => {
  void theme;
  if (!host || !legend) return;
  const css = getComputedStyle(host);
  const v = (name: string) => css.getPropertyValue(name).trim();
  const [divisor, unitName] = scale;
  const domain = lines.map((l) => l.short);
  const colours = domain.map((_, i) => v(`--s${(i % SLOTS) + 1}`));
  const labels = steps.map((s) => s[0]?.label ?? "");
  const ticks = ticksFor(
    steps.map((s) => ({ label: s[0]?.label ?? "", released: s[0]?.released ?? false })),
    Math.floor(width / 72),
  );
  const data = points.map((p) => ({
    ...p,
    y: p.value / divisor,
    lo: (p.lower ?? p.value) / divisor,
    hi: (p.upper ?? p.value) / divisor,
  }));
  const tips = steps.map((s) => ({
    label: s[0]?.label ?? "",
    y: Math.max(...s.map((p) => p.value)) / divisor,
    text: describe(s),
  }));
  const ys = data.map((d) => d.y);
  const [low, high] = [Math.min(...ys), Math.max(...ys)];
  const pad = (high - low) * 0.15 || Math.abs(high) * 0.05 || 1;
  const yDomain = [Math.max(0, low - pad), high + pad];
  const valueAt = new Map(points.map((p) => [`${p.commit}/${p.short}`, p.value / divisor]));
  // Rings at one release grow by a step each, so rings on lines that coincide stay apart.
  const flagged = [...changeAt.entries()].flatMap(([commit, cs]) =>
    cs
      .filter((c) => c.change.method === "release")
      .map((c) => ({
        label: points.find((p) => p.commit === commit)?.label ?? "",
        y: valueAt.get(`${commit}/${c.short}`),
        way: verdict(c.change.ratio, better),
      }))
      .filter((f) => f.y !== undefined)
      .map((f, tier) => ({ ...f, tier })),
  );
  const tiers = [...new Set(flagged.map((f) => f.tier))];
  const ring = (d: { way: string }) =>
    d.way === "worse" ? v("--worse") : d.way === "better" ? v("--better") : v("--ink");
  const shifts = [
    ...new Set(
      [...changeAt.entries()]
        .filter(([, cs]) => cs.some((c) => c.change.method === "change-point"))
        .map(([commit]) => points.find((p) => p.commit === commit)?.label ?? ""),
    ),
  ];
  const picked = active === null ? undefined : tips[active];
  const plot = Plot.plot({
    width,
    height: width < 480 ? 300 : 380,
    marginLeft: 56,
    marginRight: 16,
    marginTop: 24,
    marginBottom: 36,
    ariaLabel: `${title}, ${unitName} per release`,
    style: { color: v("--ink-2"), fontSize: "12px", fontFamily: "inherit", overflow: "visible" },
    x: { type: "point", domain: labels, ticks, label: null, padding: 0.3 },
    // From the values, not the intervals: one wide interval would otherwise flatten every line.
    y: { label: unitName, grid: true, nice: true, domain: yDomain, tickFormat: (d: number) => sig(d) },
    color: { domain, range: colours },
    symbol: { domain, range: domain.map((_, i) => SYMBOLS[i % SYMBOLS.length] ?? "circle") },
    marks: [
      Plot.gridY({ stroke: v("--grid"), strokeOpacity: 1 }),
      Plot.ruleX(shifts, { stroke: v("--shift"), strokeDasharray: "4 4", strokeWidth: 1 }),
      Plot.text(shifts, { x: (d: string) => d, frameAnchor: "top", dy: -14, text: () => "shift", fill: v("--ink-2") }),
      Plot.areaY(data, { x: "label", y1: "lo", y2: "hi", z: "short", fill: "short", fillOpacity: 0.12, clip: true }),
      Plot.lineY(data, { x: "label", y: "y", z: "short", stroke: "short", strokeWidth: 2 }),
      // Outlined, so a symbol under another of a different shape still shows.
      Plot.dot(data, { x: "label", y: "y", fill: "none", stroke: "short", symbol: "short", r: 4, strokeWidth: 1.5 }),
      ...tiers.map((t) =>
        Plot.dot(
          flagged.filter((f) => f.tier === t),
          { x: "label", y: "y", r: 9 + 4 * t, fill: "none", strokeWidth: 2, stroke: ring },
        ),
      ),
      picked ? Plot.ruleX([picked.label], { stroke: v("--ink"), strokeOpacity: 0.4 }) : null,
      Plot.tip(tips, Plot.pointerX({ x: "label", y: "y", title: "text", fill: v("--surface"), stroke: v("--axis") })),
      picked
        ? Plot.tip([picked], {
            x: "label",
            y: "y",
            title: "text",
            fill: v("--surface"),
            stroke: v("--axis"),
          })
        : null,
    ],
  });
  // Plot labels each mark's group without giving it a role, which axe rejects (aria-prohibited-attr).
  // The pointer's tip is drawn again on each move, so new groups get the same treatment.
  const unlabel = () => {
    for (const g of plot.querySelectorAll("g[aria-label]")) {
      g.setAttribute("data-mark", g.getAttribute("aria-label") ?? "");
      g.removeAttribute("aria-label");
    }
  };
  unlabel();
  const watch = new MutationObserver(unlabel);
  watch.observe(plot, { childList: true, subtree: true });
  const key = plot.legend("symbol");
  host.replaceChildren(plot);
  legend.replaceChildren(...(key && lines.length > 1 ? [key] : []));
  figure = plot as unknown as SVGSVGElement;
  return () => watch.disconnect();
});

function onkey(e: KeyboardEvent) {
  const last = steps.length - 1;
  const move = ({ ArrowRight: 1, ArrowLeft: -1, PageDown: 5, PageUp: -5 } as Record<string, number>)[e.key];
  if (move !== undefined) active = Math.min(last, Math.max(0, (active ?? (move > 0 ? -1 : last + 1)) + move));
  else if (e.key === "Home") active = 0;
  else if (e.key === "End") active = last;
  else if (e.key === "Escape") active = null;
  else return;
  e.preventDefault();
}

/** The chart as a standalone SVG file, its colours already resolved. */
function download() {
  if (!figure || !host) return;
  const copy = figure.cloneNode(true) as SVGSVGElement;
  copy.setAttribute("xmlns", "http://www.w3.org/2000/svg");
  copy.querySelectorAll("[data-mark='tip']").forEach((t) => {
    t.remove();
  });
  const bg = getComputedStyle(host).getPropertyValue("--surface").trim();
  const text = copy.outerHTML
    .replace(/var\(--plot-background\)/g, bg)
    .replace(/<svg([^>]*?) style="/, `<svg$1 style="background:${bg};font-family:system-ui,sans-serif;`);
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([text], { type: "image/svg+xml" }));
  a.download = `${filename}.svg`;
  a.click();
  URL.revokeObjectURL(a.href);
}

const said = $derived.by(() => {
  const step = active === null ? undefined : steps[active];
  return step ? describe(step).replaceAll("\n", "; ") : "";
});
</script>

<div class="legend-host" bind:this={legend}></div>
<!-- svelte-ignore a11y_no_noninteractive_tabindex, a11y_no_noninteractive_element_interactions -->
<div
  class="chart"
  bind:this={host}
  bind:clientWidth={width}
  role="group"
  tabindex="0"
  aria-label="{title}. Left and right arrow keys step through the releases; the data table below holds every value."
  aria-describedby="chart-help"
  onkeydown={onkey}
  onblur={() => (active = null)}
></div>
<p class="sr" aria-live="polite">{said}</p>
<div class="actions">
  <p id="chart-help" class="hint">Focus the chart, then use the arrow keys, Home and End to read each release.</p>
  <button type="button" onclick={download}>Download SVG</button>
</div>
