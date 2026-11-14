<script lang="ts">
import type { Ratios } from "../lib/contract";
import { dateLabel } from "../lib/guidance";
import { sig } from "../lib/history";
import { ratioScale } from "../lib/ratio-scale";
import { scrollable } from "../lib/scrollable";

// `ratios`: undefined while loading or when none are published (`ready` tells which).
let {
  ratios,
  ready,
  error,
  method,
}: { ratios: Ratios | undefined; ready: boolean; error: string | undefined; method: string | undefined } = $props();

type Row = Ratios["comparisons"][number]["candidates"][number]["rows"][number];
const machines = $derived(new Map((ratios?.machines ?? []).map((m) => [m.id, m])));
const oses = $derived([...new Set((ratios?.machines ?? []).map((m) => m.os))]);
const TIERS = { reference: "Reference", hosted: "Hosted", contributed: "Contributed, unverified" };
const ms = (s: number) => `${sig(s * 1000)} ms`;
const tone = (way: string) => (way === "faster" ? "better" : way === "slower" ? "worse" : "");
type Comparison = Ratios["comparisons"][number];
// The case and params most tables time, described once above them; a table names its own only when it differs.
const caseOf = (c: Comparison) => JSON.stringify([c.case, c.params]);
const shared = $derived.by(() => {
  const all = ratios?.comparisons ?? [];
  const count = (c: Comparison) => all.filter((d) => caseOf(d) === caseOf(c)).length;
  const most = all.reduce<Comparison | undefined>((a, c) => (a && count(a) >= count(c) ? a : c), undefined);
  return most && count(most) > 1 ? most : undefined;
});
const interval = (r: Row) => (r.ci95 ? `${sig(r.ci95[0])} to ${sig(r.ci95[1])}` : "");
</script>

<header class="overview-intro compare-intro">
  <h2>Across machines</h2>
  <p class="lede">
    Does a choice that speeds up Brightway on one computer do the same on yours? Each table times one choice against
    the usual one on several machines{oses.length ? `: ${oses.join(", ")}` : ""}, one row per machine.
  </p>
</header>

{#if error}
  <div class="empty" role="alert">
    <p>The comparisons could not load. The benchmark histories remain available.</p>
    <details class="technical"><summary>Technical details</summary><p class="mono">{error}</p></details>
  </div>
{:else if !ready}
  <div class="skeleton" aria-busy="true"><span class="sr">Loading the comparisons…</span></div>
{:else if !ratios}
  <p class="empty" role="status">
    No comparisons are published yet. A weekly run times them on GitHub's Linux, macOS and Windows runners, and they
    appear here after its first run.
  </p>
{:else}
  <dl class="compare-key">
    <dt>Ratio</dt>
    <dd>The alternative's time divided by the usual choice's, from runs taken in turns on the same machine. Below 1 the alternative is faster.</dd>
    <dt>Interval</dt>
    <dd>The ratio's 95% interval, drawn as a bar on a log scale. A bar that reaches the line at 1 shows no clear difference on that machine.</dd>
    <dt>Summary</dt>
    <dd>Under each choice: the range over the reference and hosted machines where the difference is clear, or "Differs between machines" when they disagree, and how many show no clear difference. Contributed machines count only when no other machine measured the choice.</dd>
    <dt>Source</dt>
    <dd>Hosted rows ran in this project's weekly workflow, which signs each file. Contributed rows come from other people's machines and are not verified.{#if method}{" "}<a href={method}>How the ratios are measured</a>.{/if}</dd>
  </dl>

  {#if shared}<p class="ratio-case ratio-shared">Unless a table says otherwise, each times {@render about(shared)}</p>{/if}

  {#each ratios.comparisons as c (c.key)}
    <section class="ratio-comparison" aria-labelledby="ratio-{c.key}">
      <h3 id="ratio-{c.key}">{c.title}</h3>
      {#if !shared || caseOf(c) !== caseOf(shared)}<p class="ratio-case">{@render about(c)}</p>{/if}
      {#if c.caveat}<p class="ratio-case">{c.caveat}</p>{/if}
      <div class="scroll" role="region" aria-label="{c.title}, table" use:scrollable>
        <!-- svelte-ignore a11y_no_redundant_roles -->
        <!-- Explicit roles: phones lay the table out as blocks, which can drop its semantics in Chromium and WebKit. -->
        <table class="ratio-table" role="table">
          <caption class="sr">{c.title}: one row per machine; below 1 the alternative is faster.</caption>
          <!-- svelte-ignore a11y_no_redundant_roles -->
          <thead role="rowgroup">
            <!-- svelte-ignore a11y_no_redundant_roles -->
            <tr role="row">
              <th role="columnheader" scope="col">Machine</th>
              <th role="columnheader" scope="col">Source</th>
              <th role="columnheader" scope="col" class="num">Ratio</th>
              <th role="columnheader" scope="col" class="num">95% interval</th>
              <th role="columnheader" scope="col" class="ratio-axis-head"><span aria-hidden="true"><span>faster</span><span>slower</span></span><span class="sr">Interval drawn around 1</span></th>
              <th role="columnheader" scope="col">Reading</th>
            </tr>
          </thead>
          {#each c.candidates as k (k.name)}
            {@const x = ratioScale(k.rows)}
            <!-- svelte-ignore a11y_no_redundant_roles -->
            <tbody role="rowgroup">
              <!-- svelte-ignore a11y_no_redundant_roles -->
              <tr class="ratio-candidate" role="row">
                <th role="rowheader" scope="rowgroup" colspan="6">
                  <span class="ratio-label">{k.label}</span>
                  <span class="ratio-summary {c.caveat ? 'muted' : tone(k.summary.direction)}">{k.summary.text}</span>
                </th>
              </tr>
              {#each k.rows as r (r.machine)}
                {@const m = machines.get(r.machine)}
                <!-- svelte-ignore a11y_no_redundant_roles -->
                <tr class="ratio-row" role="row">
                  <th role="rowheader" scope="row">
                    {m?.name ?? r.machine}
                    <span class="ratio-meta">{m?.os}{m?.cpu ? ` · ${m.cpu}` : ""}</span>
                  </th>
                  <td class="ratio-source" role="cell" data-label="Source">
                    {m ? TIERS[m.tier] : ""}
                    {#if m}<span class="ratio-meta">{#if m.run}<a href={m.run}>{dateLabel(m.created)}<span class="sr">, the run</span></a>{:else}{dateLabel(m.created)}{/if}</span>{/if}
                  </td>
                  <td class="num" role="cell" data-label="Ratio">{r.ratio === null ? "–" : sig(r.ratio)}</td>
                  <td class="num" role="cell" data-label="95% interval">{r.ci95 ? interval(r) : "–"}</td>
                  <td class="ratio-graphic" role="cell" data-label="Interval">
                    <!-- Phones only, where the column header is hidden: "1" over the line at 1, the two directions under the ends. -->
                    <div class="ratio-axis" aria-hidden="true"><span class="ratio-one-label" style:left="{x(1)}%">1</span></div>
                    <div class="ratio-track" aria-hidden="true">
                      <span class="ratio-one" style:left="{x(1)}%"></span>
                      {#if r.ci95 && r.ratio !== null}
                        <span class="ratio-bar {tone(r.verdict)}" style:left="{x(r.ci95[0])}%" style:width="{Math.max(x(r.ci95[1]) - x(r.ci95[0]), 0.5)}%"></span>
                        <span class="ratio-dot {tone(r.verdict)}" style:left="{x(r.ratio)}%"></span>
                      {/if}
                    </div>
                    <div class="ratio-axis" aria-hidden="true"><span>faster</span><span>slower</span></div>
                  </td>
                  <td class="ratio-reading" role="cell" data-label="Reading">
                    <span class={tone(r.verdict)}>{r.text}</span>
                    {#if r.missing}<span class="ratio-meta">{r.missing}</span>
                    {:else if r.seconds}<span class="ratio-meta">{ms(r.seconds.candidate)} against {ms(r.seconds.baseline)}</span>{/if}
                  </td>
                </tr>
              {/each}
            </tbody>
          {/each}
        </table>
      </div>
    </section>
  {/each}
{/if}

{#snippet about(c: Comparison)}
  <strong>{c.case_name}</strong>{c.description ? `: ${c.description}` : ""}
  {#each c.params as p (p.name)}{" "}<span>{p.name}: <strong>{p.value}</strong>{p.note ? ` (${p.note.replace(/\.$/, "")})` : ""}.</span>{/each}
{/snippet}

<style>
  .compare-key {
    display: grid;
    grid-template-columns: max-content minmax(0, 1fr);
    gap: 6px 18px;
    max-width: 76ch;
    margin: 4px 0 0;
    color: var(--ink-2);
    font-size: var(--text-evidence);
    line-height: 1.55;
  }
  .compare-key dt {
    font-weight: 650;
    color: var(--ink);
  }
  .compare-key dd {
    margin: 0;
  }
  .ratio-comparison {
    margin-top: 44px;
  }
  .ratio-case.ratio-shared {
    margin-top: 20px;
  }
  .ratio-comparison h3 {
    font-size: 1.35rem;
    font-weight: 650;
    letter-spacing: -0.02em;
    margin: 0 0 6px;
    padding-top: 16px;
    border-top: 2px solid var(--ink);
  }
  .ratio-case {
    max-width: 76ch;
    margin: 0 0 8px;
    color: var(--ink-2);
    font-size: var(--text-evidence);
  }
  .ratio-case strong {
    color: var(--ink);
    font-weight: 600;
  }
  .ratio-table th,
  .ratio-table td {
    vertical-align: middle;
    padding: 10px 18px 10px 0;
    font-size: var(--text-evidence);
  }
  .ratio-table thead th {
    font-size: var(--text-meta);
  }
  .ratio-table td.num {
    font-size: 1rem;
  }
  .ratio-candidate th {
    padding-top: 26px;
    border-bottom-color: var(--axis);
    font-weight: 400;
  }
  .ratio-candidate:hover,
  .ratio-candidate th {
    background: var(--page);
  }
  .ratio-label {
    display: inline-block;
    margin-right: 14px;
    color: var(--ink);
    font-size: 1.05rem;
    font-weight: 650;
  }
  .ratio-summary {
    font-weight: 600;
  }
  .ratio-summary.muted {
    color: var(--muted);
  }
  .ratio-row th {
    font-weight: 550;
  }
  .ratio-meta {
    display: block;
    margin-top: 2px;
    color: var(--muted);
    font-size: var(--text-meta);
    font-weight: 400;
    overflow-wrap: anywhere;
  }
  .ratio-reading .ratio-meta {
    max-width: 32ch;
  }
  .ratio-axis-head,
  .ratio-graphic {
    width: 26%;
    min-width: 150px;
  }
  .ratio-axis-head > span[aria-hidden] {
    display: flex;
    justify-content: space-between;
    color: var(--muted);
    font-weight: 400;
  }
  .ratio-track {
    position: relative;
    height: 22px;
  }
  .ratio-track > span {
    position: absolute;
  }
  .ratio-one {
    top: 0;
    bottom: 0;
    width: 1px;
    background: var(--ink-2);
  }
  .ratio-bar {
    top: 9px;
    height: 4px;
    background: var(--axis);
  }
  .ratio-dot {
    top: 5px;
    width: 12px;
    height: 12px;
    margin-left: -6px;
    border-radius: 50%;
    background: var(--muted);
    box-shadow: 0 0 0 2px var(--page);
  }
  .ratio-bar.better,
  .ratio-dot.better {
    background: var(--better);
  }
  .ratio-bar.worse,
  .ratio-dot.worse {
    background: var(--worse);
  }
  .ratio-axis {
    display: none;
  }
  @media (forced-colors: active) {
    .ratio-track > span {
      forced-color-adjust: none;
      background: CanvasText;
      box-shadow: none;
    }
  }
  /* Phones: each machine becomes a block, its interval drawn full width under its name. */
  @media (max-width: 39rem) {
    .ratio-table,
    .ratio-table tbody,
    .ratio-table tr,
    .ratio-table th,
    .ratio-table td {
      display: block;
    }
    .ratio-table thead {
      position: absolute;
      width: 1px;
      height: 1px;
      overflow: hidden;
      clip-path: inset(50%);
    }
    .ratio-table .ratio-row {
      display: grid;
      grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
      gap: 6px 16px;
      padding: 14px 0;
      border-bottom: 1px solid var(--grid);
    }
    .ratio-table .ratio-row > * {
      border: 0;
      padding: 0;
      width: auto;
      min-width: 0;
    }
    .ratio-row th,
    .ratio-graphic,
    .ratio-reading {
      grid-column: 1 / -1;
    }
    .ratio-row td.num {
      text-align: left;
      white-space: normal;
    }
    .ratio-row td::before {
      content: attr(data-label);
      content: attr(data-label) / "";
      display: block;
      color: var(--muted);
      font-size: var(--text-meta);
    }
    .ratio-source {
      grid-column: 1 / -1;
    }
    .ratio-axis {
      display: flex;
      justify-content: space-between;
      position: relative;
      min-height: 1.2em;
      color: var(--muted);
      font-size: var(--text-meta);
      line-height: 1.2;
    }
    .ratio-one-label {
      position: absolute;
      transform: translateX(-50%);
    }
    .ratio-candidate th {
      padding: 22px 0 10px;
    }
    .ratio-label {
      display: block;
      margin: 0 0 2px;
    }
  }
</style>
