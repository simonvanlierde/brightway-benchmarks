<script lang="ts">
import type { BenchmarkIndex } from "../lib/contract";
import { benchmarkLabel, latestChanges, noiseText, percent, type View, writeView } from "../lib/history";

let {
  index,
  view,
  go,
  follow,
}: { index: BenchmarkIndex; view: View; go: (next: View) => void; follow: (event: MouseEvent, next: View) => void } =
  $props();
const latest = $derived(latestChanges(index));
const exported = $derived(index.changes !== undefined);
const packageId = $derived(view.group ?? "");
const direction = $derived(["worse", "better"].includes(view.direction ?? "") ? view.direction : "all");
const packageChanges = $derived(latest.filter((r) => !packageId || r.group.id === packageId));
const filtered = $derived(packageChanges.filter((r) => direction === "all" || r.way === direction));
const worse = $derived(packageChanges.filter((r) => r.way === "worse").length);
const better = $derived(packageChanges.filter((r) => r.way === "better").length);
function labelOf(b: BenchmarkIndex["benchmarks"][number]): string {
  const label = benchmarkLabel(b.name);
  return index.benchmarks.filter((other) => other.group === b.group && benchmarkLabel(other.name) === label).length > 1
    ? `${label} (${b.name})`
    : label;
}
</script>
        <header>
          <h2>What moved in the latest releases</h2>
          <p class="lede">
            The latest release of each package, compared with the one before it. Only changes beyond measurement noise appear here.
          </p>
        </header>
        <div class="overview-toolbar">
          <div class="direction-filter" role="group" aria-label="Filter changes">
            <button class:chosen={direction === "all"} aria-pressed={direction === "all"} onclick={() => go({ ...view, direction: "all" })}>All changes <span>{packageChanges.length}</span></button>
            <button class:chosen={direction === "worse"} aria-pressed={direction === "worse"} onclick={() => go({ ...view, direction: "worse" })}>Worse <span class="worse">{worse}</span></button>
            <button class:chosen={direction === "better"} aria-pressed={direction === "better"} onclick={() => go({ ...view, direction: "better" })}>Better <span class="better">{better}</span></button>
          </div>
          <div class="package-filter"><label class="sr" for="package-filter">Package</label><select id="package-filter" value={packageId} onchange={(e) => go({ ...view, group: e.currentTarget.value })}><option value="">All packages</option>{#each index.groups as g (g.id)}<option value={g.id}>{g.name}</option>{/each}</select></div>
        </div>
        {#if !exported}
          <p class="empty">Changes were not exported with this data, so there is nothing to compare here.</p>
        {:else if latest.length === 0}
          <p class="empty">Nothing moved beyond its noise in any package's latest release.</p>
        {:else if filtered.length === 0}
          <p class="empty">No changes match these filters. Choose another package or change direction.</p>
        {:else}
          <!-- svelte-ignore a11y_no_noninteractive_tabindex: a scrolling region must take focus to scroll by keyboard -->
          <div class="scroll gap" role="region" aria-label="Latest changes" tabindex="0">
            <table class="latest-table responsive-table">
              <caption>
                {filtered.length} changes shown. Worse first, then the largest change; noise is the threshold each change exceeded.
              </caption>
              <thead>
                <tr>
                  <th scope="col">Benchmark</th>
                  <th scope="col" class="num">Change</th>
                  <th scope="col">Environment</th>
                  <th scope="col">Releases</th>
                </tr>
              </thead>
              <tbody>
                {#each filtered as row, i (i)}
                  {@const next = { bench: row.bench.id, params: row.params, measure: row.change.measure, machine: row.change.machine }}
                  <tr>
                    <th scope="row" class="wrap">
                      <span class="package-name">{row.group.name}</span><br />
                      <a href={writeView(next)} onclick={(e) => follow(e, next)}
                         title={row.bench.name}>{labelOf(row.bench)}</a
                      >
                      {#if row.params.length}<br /><span class="quiet">{row.params.join(", ")}</span>{/if}
                    </th>
                    <td class="num" data-label="Change">
                      <span class="delta {row.way}">{percent(row.change.ratio)} {row.way}</span><br />
                      <span class="quiet">noise {noiseText(row.change)}</span>
                    </td>
                    <td class="wrap" data-label="Environment">{row.env}{#if index.machines.length > 1}<br /><span class="quiet">{index.machines.find((m) => m.id === row.change.machine)?.name ?? row.change.machine}</span>{/if}</td>
                    <td class="nowrap" data-label="Releases">{row.from} <span class="quiet">→</span> {row.to}</td>
                  </tr>
                {/each}
              </tbody>
            </table>
          </div>
        {/if}
