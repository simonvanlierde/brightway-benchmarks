<script lang="ts">
import type { BenchmarkIndex } from "../lib/contract";
import { benchmarkLabel, byBenchmark, latestChanges, noiseText, percent, type View, writeView } from "../lib/history";

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
const flagged = $derived(filtered.filter((r) => r.way !== "better"));
const gains = $derived(byBenchmark(filtered.filter((r) => r.way === "better")));
const gainCases = $derived(gains.reduce((n, g) => n + g.rows.length, 0));
const narrowed = $derived(packageId !== "" || direction !== "all");
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
            <button class:chosen={direction === "all"} aria-pressed={direction === "all"} onclick={() => go({ ...view, page: "changes", direction: "all" })}>All changes <span>{packageChanges.length}</span></button>
            <button class:chosen={direction === "worse"} aria-pressed={direction === "worse"} onclick={() => go({ ...view, page: "changes", direction: "worse" })}>Worse <span class="worse">{worse}</span></button>
            <button class:chosen={direction === "better"} aria-pressed={direction === "better"} onclick={() => go({ ...view, page: "changes", direction: "better" })}>Better <span class="better">{better}</span></button>
          </div>
          <div class="package-filter"><label class="sr" for="package-filter">Package</label><select id="package-filter" value={packageId} onchange={(e) => go({ ...view, page: "changes", group: e.currentTarget.value })}><option value="">All packages</option>{#each index.groups as g (g.id)}<option value={g.id}>{g.name}</option>{/each}</select></div>
        </div>
        <p class="sr" role="status">{filtered.length} of {packageChanges.length} changes shown</p>
        {#if narrowed}<button type="button" class="clear-filters" onclick={() => go({ ...view, page: "changes", group: "", direction: "all" })}>Clear filters</button>{/if}
        {#if !exported}
          <p class="empty">Changes were not exported with this data, so there is nothing to compare here.</p>
        {:else if latest.length === 0}
          <p class="empty">Nothing moved beyond its noise in any package's latest release.</p>
        {:else if filtered.length === 0}
          <p class="empty">No changes match these filters. Choose another package or change direction.</p>
        {:else}
          {#if flagged.length}
          <h3 id="flagged-h">Regressions</h3>
          <!-- svelte-ignore a11y_no_noninteractive_tabindex: a scrolling region must take focus to scroll by keyboard -->
          <div class="scroll gap" role="region" aria-labelledby="flagged-h" tabindex="0">
            <table class="latest-table responsive-table">
              <caption>
                Largest first, each beside the noise it exceeded.
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
                {#each flagged as row, i (i)}
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
                      <span class="quiet">beyond {noiseText(row.change)} noise</span>
                    </td>
                    <td class="wrap" data-label="Environment">{row.env}{#if index.machines.length > 1}<br /><span class="quiet">{index.machines.find((m) => m.id === row.change.machine)?.name ?? row.change.machine}</span>{/if}</td>
                    <td class="nowrap" data-label="Releases">{row.from} <span class="quiet">→</span> {row.to}</td>
                  </tr>
                {/each}
              </tbody>
            </table>
          </div>
          {/if}
          {#if gains.length}
          <h3 id="gains-h">Improvements</h3>
          <!-- svelte-ignore a11y_no_noninteractive_tabindex: a scrolling region must take focus to scroll by keyboard -->
          <div class="scroll gap" role="region" aria-labelledby="gains-h" tabindex="0">
            <table class="latest-table gains-table responsive-table">
              <caption>
                {gains.length} {gains.length === 1 ? "benchmark" : "benchmarks"} with {gainCases} improved {gainCases === 1 ? "case" : "cases"}; open the cases for each environment and its noise.
              </caption>
              <thead>
                <tr>
                  <th scope="col">Benchmark</th>
                  <th scope="col" class="num">Change</th>
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
                        <span class="package-name">{g.group.name}</span><br />
                        <a href={writeView(next)} onclick={(e) => follow(e, next)} title={g.bench.name}>{labelOf(g.bench)}</a>
                      </th>
                      <td class="num" data-label="Change">
                        <span class="delta better">{g.rows.length > 1 ? `${percent(low.change.ratio)} to ${percent(top.change.ratio)}` : percent(top.change.ratio)} better</span>
                      </td>
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
                      <td class="nowrap" data-label="Releases">{top.from} <span class="quiet">→</span> {top.to}</td>
                    </tr>
                  {/if}
                {/each}
              </tbody>
            </table>
          </div>
          {/if}
        {/if}
