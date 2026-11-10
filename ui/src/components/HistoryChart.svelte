<script lang="ts">
import * as Plot from "@observablehq/plot";
import type { Change } from "../lib/contract";
import { format, type Line, noiseText, percent, scaleFor, sig, ticksFor, verdict } from "../lib/history";
import { spreadLabels } from "../lib/labels";

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
let picked = $state<string | null>(null); // the environment its legend button brings forward
let host = $state<HTMLElement>();
let legend = $state<HTMLElement>();
let figure = $state<SVGSVGElement>();

$effect(() => {
  const media = matchMedia("(prefers-color-scheme: dark)");
  const bump = () => theme++;
  media.addEventListener("change", bump);
  document.addEventListener("bwbench:theme", bump);
  return () => {
    media.removeEventListener("change", bump);
    document.removeEventListener("bwbench:theme", bump);
  };
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
  if (change.method === "release") return `${percent(change.ratio)} ${way} (beyond ${noiseText(change)} noise)`;
  return `level shift ${percent(change.ratio)} ${way}`;
}

function stepText(step: (typeof steps)[number]): string {
  const [first] = step;
  if (!first) return "";
  const rows = step.map(
    (p) =>
      `${p.short}: ${format(p.value, unit)}${p.noise === undefined ? "" : ` ${noiseText({ threshold: p.noise })} noise`}`,
  );
  const marks = (changeAt.get(first.commit) ?? []).map((c) => `${c.short}: ${words(c.change)}`);
  const note = first.released ? [] : ["Not a release, so release changes skip it"];
  return [`${first.label} · ${first.date}`, ...rows, ...marks, ...note].join("\n");
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
    lo: (p.noise === undefined ? (p.lower ?? p.value) : p.value * (1 - p.noise)) / divisor,
    hi: (p.noise === undefined ? (p.upper ?? p.value) : p.value * (1 + p.noise)) / divisor,
  }));
  const tips = steps.map((s) => ({
    label: s[0]?.label ?? "",
    y: Math.max(...s.map((p) => p.value)) / divisor,
    text: stepText(s),
  }));
  const ys = data.map((d) => d.y);
  const [low, high] = [Math.min(...ys), Math.max(...ys)];
  const pad = (high - low) * 0.15 || Math.abs(high) * 0.05 || 1;
  const yDomain = [Math.max(0, low - pad), high + pad];
  const valueAt = new Map(points.map((p) => [`${p.commit}/${p.short}`, p.value / divisor]));
  // Rings at one release grow by a step each, so rings on lines that coincide stay apart (unless set apart by dx).
  const flagged = [...changeAt.entries()].flatMap(([commit, cs]) =>
    cs
      .filter((c) => c.change.method === "release")
      .map((c) => ({
        label: points.find((p) => p.commit === commit)?.label ?? "",
        y: valueAt.get(`${commit}/${c.short}`),
        short: c.short,
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
  const at = active === null ? undefined : tips[active];
  const chosen = picked !== null && domain.includes(picked) ? picked : null;
  const fade = (d: { short: string }) => (chosen && d.short !== chosen ? 0.2 : 1);
  // A commit that is not a release draws fainter: release changes do not compare it.
  const faint = (d: { short: string; released: boolean }) => fade(d) * (d.released ? 1 : 0.45);
  // Two releases make a before and after, not a trend, so they get no connecting line.
  const joined = labels.length > 2;
  // With few steps there is room to set each environment a little apart, so equal values stay visible.
  const spread =
    labels.length <= 3 && domain.length > 1 ? Math.min(20, width / (labels.length * 3 * domain.length)) : 0;
  const series = domain.map((name, i) => ({ name, dx: (i - (domain.length - 1) / 2) * spread }));
  // End-of-line names where they fit; the legend above stays as the fallback and the way to focus a line.
  const labelled = width >= 640 && domain.length > 1;
  const labelRoom = labelled ? Math.min(160, Math.ceil(Math.max(...domain.map((n) => n.length)) * 6.8) + 18) : 16;
  const emphasis = (name: string) => name === chosen;
  const plot = Plot.plot({
    width,
    height: width < 480 ? 300 : 380,
    marginLeft: 56,
    marginRight: labelRoom,
    marginTop: 24,
    marginBottom: 36,
    ariaLabel: `${title}, ${unitName} per release`,
    style: { color: v("--ink-2"), fontSize: "12px", fontFamily: "inherit", overflow: "visible" },
    x: { type: "point", domain: labels, ticks, label: null, padding: 0.3 },
    // From the values, not the intervals: one wide interval would otherwise flatten every line.
    y: {
      label: unitName,
      grid: true,
      nice: true,
      ticks: width < 480 ? 4 : 6,
      domain: yDomain,
      tickFormat: (d: number) => sig(d),
    },
    color: { domain, range: colours },
    symbol: { domain, range: domain.map((_, i) => SYMBOLS[i % SYMBOLS.length] ?? "circle") },
    marks: [
      Plot.gridY({ stroke: v("--grid"), strokeOpacity: 1 }),
      Plot.ruleX(shifts, { stroke: v("--shift"), strokeDasharray: "4 4", strokeWidth: 1 }),
      Plot.text(shifts, { x: (d: string) => d, frameAnchor: "top", dy: -14, text: () => "shift", fill: v("--ink-2") }),
      ...series.flatMap(({ name, dx }) => {
        const mine = data.filter((d) => d.short === name);
        return [
          joined
            ? Plot.areaY(mine, { x: "label", y1: "lo", y2: "hi", dx, fill: "short", fillOpacity: 0.12, clip: true })
            : null,
          joined
            ? Plot.lineY(mine, {
                x: "label",
                y: "y",
                dx,
                stroke: "short",
                strokeWidth: emphasis(name) ? 3.5 : 2,
                strokeOpacity: fade,
              })
            : null,
          // Outlined, so a symbol under another of a different shape still shows.
          Plot.dot(mine, {
            x: "label",
            y: "y",
            dx,
            fill: "none",
            stroke: "short",
            symbol: "short",
            r: (joined ? 5 : 6) + (emphasis(name) ? 2 : 0),
            strokeWidth: emphasis(name) ? 2.5 : 1.5,
            strokeOpacity: faint,
          }),
          ...tiers.map((t) =>
            Plot.dot(
              flagged.filter((f) => f.tier === t && f.short === name),
              { x: "label", y: "y", dx, r: spread ? 9 : 9 + 4 * t, fill: "none", strokeWidth: 2, stroke: ring },
            ),
          ),
        ];
      }),
      at ? Plot.ruleX([at.label], { stroke: v("--ink"), strokeOpacity: 0.4 }) : null,
      Plot.tip(tips, Plot.pointerX({ x: "label", y: "y", title: "text", fill: v("--page"), stroke: v("--axis") })),
      at
        ? Plot.tip([at], {
            x: "label",
            y: "y",
            title: "text",
            fill: v("--page"),
            stroke: v("--axis"),
          })
        : null,
    ],
  });
  const x = labelled ? plot.scale("x") : undefined;
  const y = labelled ? plot.scale("y") : undefined;
  // An empty series has no scales, so no end labels.
  if (x && y) {
    const last = Math.max(...data.map((d) => d.at));
    const ends = series
      .flatMap(({ name, dx }) => {
        const end = data.find((d) => d.short === name && d.at === last) ?? data.filter((d) => d.short === name).at(-1);
        return end ? [{ name, dx, x: x.apply(end.label) as number, y: y.apply(end.y) as number }] : [];
      })
      .sort((a, b) => a.y - b.y);
    // Names that would touch are pushed apart, 14px a line, and kept inside the plot.
    const floor = Number(plot.getAttribute("height")) - 36;
    const placed = spreadLabels(
      ends.map((e) => e.y),
      floor,
    );
    for (const [i, e] of ends.entries()) e.y = placed[i] ?? e.y;
    for (const e of ends) {
      const text = document.createElementNS("http://www.w3.org/2000/svg", "text");
      text.setAttribute("x", String(e.x + e.dx + 12));
      text.setAttribute("y", String(e.y));
      text.setAttribute("dominant-baseline", "central");
      text.setAttribute("text-anchor", "start"); // the plot's own style centres text
      text.setAttribute("fill", v("--ink-2"));
      text.setAttribute("data-end-label", e.name);
      if (chosen && e.name !== chosen) text.setAttribute("opacity", "0.8");
      if (emphasis(e.name)) text.setAttribute("font-weight", "650");
      text.textContent = e.name;
      plot.append(text);
    }
  }
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
  // Each swatch becomes a button that brings its environment forward; the redraw keeps focus on it.
  const had = (document.activeElement as HTMLElement | null)?.dataset.series;
  for (const [i, swatch] of [...(key?.querySelectorAll(":scope > span") ?? [])].entries()) {
    const name = domain[i] ?? "";
    const button = document.createElement("button");
    button.type = "button";
    button.dataset.series = name;
    button.setAttribute("aria-pressed", String(chosen === name));
    button.append(...swatch.childNodes);
    button.onclick = () => {
      picked = chosen === name ? null : name;
    };
    swatch.replaceWith(button);
  }
  host.replaceChildren(plot);
  legend.replaceChildren(...(key && lines.length > 1 ? [key] : []));
  if (had) legend.querySelector<HTMLElement>(`[data-series="${CSS.escape(had)}"]`)?.focus();
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
  const bg = getComputedStyle(host).getPropertyValue("--page").trim();
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
  return step ? stepText(step).replaceAll("\n", "; ") : "";
});
</script>

<div class="legend-host" role="group" aria-label="Highlight an environment" bind:this={legend}></div>
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
