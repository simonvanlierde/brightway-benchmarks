<script lang="ts">
import type { BenchmarkIndex, BenchmarkReport } from "../lib/contract";
import {
  benchLabel,
  byBenchmark,
  changeRange,
  type LatestChange,
  latestChanges,
  noiseText,
  percent,
  seriesOf,
  type View,
  writeView,
} from "../lib/history";
import { scrollable } from "../lib/scrollable";
import Sparkline from "./Sparkline.svelte";

// `loaded`: reports by path, as they arrive; a row draws its history once its group's reports are in.
let {
  index,
  view,
  go,
  follow,
  loaded,
}: {
  index: BenchmarkIndex;
  view: View;
  go: (next: View) => void;
  follow: (event: MouseEvent, next: View) => void;
  loaded: Map<string, BenchmarkReport>;
} = $props();
function history(row: LatestChange) {
  const reports = new Map<string, BenchmarkReport>();
  for (const r of index.reports) {
    const data = r.group === row.group.id && r.machine === row.change.machine ? loaded.get(r.path) : undefined;
    if (data) reports.set(r.commit, data);
  }
  return seriesOf(index, reports, row.change.case, row.change.measure, row.group.id);
}
const latest = $derived(latestChanges(index));
const exported = $derived(index.changes !== undefined);
// A group's id, or its name as the old asv pages' redirects give it.
const packageId = $derived(index.groups.find((g) => g.id === view.group || g.name === view.group)?.id ?? "");
const direction = $derived(["worse", "better"].includes(view.direction ?? "") ? view.direction : "all");
const packageChanges = $derived(latest.filter((r) => !packageId || r.group.id === packageId));
const filtered = $derived(packageChanges.filter((r) => direction === "all" || r.way === direction));
const worse = $derived(packageChanges.filter((r) => r.way === "worse").length);
const better = $derived(packageChanges.filter((r) => r.way === "better").length);
const flagged = $derived(byBenchmark(filtered.filter((r) => r.way !== "better")));
const gains = $derived(byBenchmark(filtered.filter((r) => r.way === "better")));
// The filter buttons count cases; the captions reconcile them with the rows, which fold a benchmark's cases.
const flaggedCases = $derived(flagged.reduce((n, g) => n + g.rows.length, 0));
const gainCases = $derived(gains.reduce((n, g) => n + g.rows.length, 0));
// Choosing Better opens the improvements; it never closes what the reader opened.
let gainsBox = $state<HTMLDetailsElement>();
$effect(() => {
  if (direction === "better" && gainsBox) gainsBox.open = true;
});
const narrowed = $derived(packageId !== "" || direction !== "all");
const labelOf = (b: BenchmarkIndex["benchmarks"][number]) => benchLabel(index, b);
</script>
<section class="release-changes" aria-labelledby="changes-heading">
        <header class="changes-header">
          <h2 id="changes-heading">What changed in the latest releases</h2>
          <p class="lede">
            Each package's latest release against the one before. Only changes beyond measurement noise are listed.
          </p>
        </header>
        <div class="overview-toolbar">
          <div class="direction-filter" role="group" aria-label="Filter changes">
            <button class:chosen={direction === "all"} aria-pressed={direction === "all"} onclick={() => go({ ...view, page: "explorer", direction: "all" })}>All changes <span>{packageChanges.length}</span></button>
            <button class:chosen={direction === "worse"} aria-pressed={direction === "worse"} onclick={() => go({ ...view, page: "explorer", direction: "worse" })}>Worse <span class="worse">{worse}</span></button>
            <button class:chosen={direction === "better"} aria-pressed={direction === "better"} onclick={() => go({ ...view, page: "explorer", direction: "better" })}>Better <span class="better">{better}</span></button>
          </div>
          <div class="package-filter"><label class="sr" for="package-filter">Package</label><select id="package-filter" value={packageId} onchange={(e) => go({ ...view, page: "explorer", group: e.currentTarget.value })}><option value="">All packages</option>{#each index.groups as g (g.id)}<option value={g.id}>{g.label ?? g.name}</option>{/each}</select></div>
        </div>
        <p class="sr" role="status">{filtered.length} of {packageChanges.length} changes shown</p>
        {#if narrowed}<button type="button" class="clear-filters" onclick={() => go({ ...view, page: "explorer", group: "", direction: "all" })}>Clear filters</button>{/if}
        {#if !exported}
          <p class="empty">Changes were not exported with this data, so there is nothing to compare here.</p>
        {:else if latest.length === 0}
          <p class="empty">Nothing moved beyond its noise in any package's latest release.</p>
        {:else if filtered.length === 0}
          <p class="empty">No changes match these filters. Choose another package or change direction.</p>
        {:else}
          {#if flagged.length}
          <h3 id="flagged-h">Regressions</h3>
          <div class="scroll gap" role="region" aria-labelledby="flagged-h" use:scrollable>
            <table class="latest-table responsive-table">
              <caption>
                {flaggedCases} {flaggedCases === 1 ? "case" : "cases"} in {flagged.length} {flagged.length === 1 ? "row" : "rows"}, one per benchmark and machine, largest first, each beside the noise it exceeded.
              </caption>
              <thead>
                <tr>
                  <th scope="col">Benchmark</th>
                  <th scope="col" class="num">Change</th>
                  <th scope="col">History</th>
                  <th scope="col">Environment</th>
                  <th scope="col">Releases</th>
                </tr>
              </thead>
              <tbody>
                {#each flagged as g (g.bench.id + g.rows[0]?.change.machine)}
                  {@const row = g.rows[0]}
                  {#if row}
                  {@const next = { bench: row.bench.id, params: row.params, measure: row.change.measure, machine: row.change.machine }}
                  <tr>
                    <th scope="row" class="wrap">
                      <span class="package-name">{row.group.label ?? row.group.name}</span><br />
                      <a href={writeView(next)} onclick={(e) => follow(e, next)}
                         title={row.bench.name}>{labelOf(row.bench)}</a
                      >
                      {#if row.params.length}<br /><span class="quiet">{row.params.join(", ")}</span>{/if}
                    </th>
                    <td class="num" data-label="Change">
                      <span class="delta {row.way}">{changeRange(g.rows)}</span>
                      {#if g.rows.length === 1}<br /><span class="quiet">beyond {noiseText(row.change)} noise</span>{/if}
                    </td>
                    <td data-label="History"><Sparkline points={history(row)} mark={row.change.commit} /></td>
                    <td class="wrap" data-label="Environment">
                      {#if g.rows.length === 1}{row.env}
                      {:else}
                        <details class="cases">
                          <summary>{g.rows.length} cases</summary>
                          <ul>{#each g.rows as r, i (i)}<li>{percent(r.change.ratio)} · {r.env}{#if r.params.join() !== row.params.join()} · {r.params.join(", ")}{/if} <span class="quiet">beyond {noiseText(r.change)} noise</span></li>{/each}</ul>
                        </details>
                      {/if}
                      {#if index.machines.length > 1}<br /><span class="quiet">{index.machines.find((m) => m.id === row.change.machine)?.name ?? row.change.machine}</span>{/if}
                    </td>
                    <td class="nowrap" data-label="Releases">{row.from} → {row.to}</td>
                  </tr>
                  {/if}
                {/each}
              </tbody>
            </table>
          </div>
          {/if}
          {#if gains.length}
          <h3 id="gains-h">Improvements</h3>
          <details class="gains" bind:this={gainsBox}>
          <summary>{gains.length} {gains.length === 1 ? "benchmark" : "benchmarks"}, {gainCases} improved {gainCases === 1 ? "case" : "cases"}</summary>
          <div class="scroll gap" role="region" aria-labelledby="gains-h" use:scrollable>
            <table class="latest-table gains-table responsive-table">
              <caption>
                {gains.length} {gains.length === 1 ? "benchmark" : "benchmarks"} with {gainCases} improved {gainCases === 1 ? "case" : "cases"}; open the cases for each environment and its noise.
              </caption>
              <thead>
                <tr>
                  <th scope="col">Benchmark</th>
                  <th scope="col" class="num">Change</th>
                  <th scope="col">History</th>
                  <th scope="col">Cases</th>
                  <th scope="col">Releases</th>
                </tr>
              </thead>
              <tbody>
                {#each gains as g (g.bench.id + g.rows[0]?.change.machine)}
                  {@const top = g.rows[0]}
                  {@const low = g.rows[g.rows.length - 1]}
                  {#if top && low}
                    {@const next = { bench: top.bench.id, params: top.params, measure: top.change.measure, machine: top.change.machine }}
                    <tr>
                      <th scope="row" class="wrap">
                        <span class="package-name">{g.group.label ?? g.group.name}</span><br />
                        <a href={writeView(next)} onclick={(e) => follow(e, next)} title={g.bench.name}>{labelOf(g.bench)}</a>
                      </th>
                      <td class="num" data-label="Change">
                        <span class="delta better">{changeRange(g.rows)}</span>
                      </td>
                      <td data-label="History"><Sparkline points={history(top)} mark={top.change.commit} /></td>
                      <td class="wrap" data-label="Cases">
                        <details class="cases">
                          <summary>{g.rows.length} {g.rows.length === 1 ? "case" : "cases"}</summary>
                          <ul>
                            {#each g.rows as row, i (i)}
                              <li>{percent(row.change.ratio)} · {row.env}{#if row.params.length} · {row.params.join(", ")}{/if} <span class="quiet">beyond {noiseText(row.change)} noise</span></li>
                            {/each}
                          </ul>
                        </details>
                      </td>
                      <td class="nowrap" data-label="Releases">{top.from} → {top.to}</td>
                    </tr>
                  {/if}
                {/each}
              </tbody>
            </table>
          </div>
          </details>
          {/if}
        {/if}
</section>
