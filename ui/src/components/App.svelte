<script lang="ts">
import {
  type BenchmarkIndex,
  type BenchmarkReport,
  ContractError,
  loadIndex,
  loadReport,
  type Report,
} from "../lib/contract";
import {
  axisLabels,
  breakable,
  changesFor,
  commitName,
  format,
  type Line,
  latestChanges,
  lines as linesOf,
  noiseText,
  paramLabels,
  percent,
  pickParams,
  pText,
  readView,
  type View,
  verdict,
  writeView,
} from "../lib/history";

let { base }: { base: string } = $props();

// Fetched with the first chart, so the start page does not load Plot.
let chartModule: Promise<typeof import("./HistoryChart.svelte")> | undefined;
const chart = () => (chartModule ??= import("./HistoryChart.svelte"));

let index = $state<BenchmarkIndex>();
let error = $state<string>();
let errorKind = $state<ContractError["kind"]>("invalid");
let view = $state<View>(readView(location.search));
let reports = $state<Map<string, BenchmarkReport>>();
let reportError = $state<string>();
let missing = $state(0); // reports that did not load; the chart draws the rest
const cache = new Map<string, Promise<BenchmarkReport>>();
// The rail is a disclosure on a phone and always open beside the view on a wide screen.
const WIDE = "(min-width: 60rem)";
let wide = $state(matchMedia(WIDE).matches);

$effect(() => {
  const media = matchMedia(WIDE);
  const set = () => {
    wide = media.matches;
  };
  media.addEventListener("change", set);
  return () => media.removeEventListener("change", set);
});

$effect(() => {
  loadIndex(base).then(
    (data) => {
      index = data;
    },
    (reason: unknown) => {
      error = String(reason);
      errorKind = reason instanceof ContractError ? reason.kind : "missing";
    },
  );
  const back = () => {
    view = readView(location.search);
  };
  addEventListener("popstate", back);
  return () => removeEventListener("popstate", back);
});

/** Show NEXT, and keep it in the URL; a new benchmark is a new history entry, a new setting is not. */
function go(next: View) {
  const push = next.bench !== view.bench;
  view = next;
  const url = writeView(next) || location.pathname;
  if (push) history.pushState(null, "", url);
  else history.replaceState(null, "", url);
  if (push) scrollTo({ top: 0 });
}

function follow(e: MouseEvent, next: View) {
  if (e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;
  e.preventDefault();
  go(next);
}

const bench = $derived(index?.benchmarks.find((b) => b.id === view.bench));
const group = $derived(bench && index?.groups.find((g) => g.id === bench.group));
const params = $derived(bench ? pickParams(bench, view.params) : []);
const measureId = $derived(bench && (bench.measures.find((m) => m === view.measure) ?? bench.measures[0]));
const measure = $derived(index?.measures.find((m) => m.id === measureId));
const machines = $derived(
  index && bench
    ? index.machines.filter((m) => index?.reports.some((r) => r.group === bench.group && r.machine === m.id))
    : [],
);
const machine = $derived(machines.find((m) => m.id === view.machine) ?? machines[0]);
const wanted = $derived<Report[]>(
  index && bench && machine ? index.reports.filter((r) => r.group === bench.group && r.machine === machine.id) : [],
);

$effect(() => {
  const list = wanted;
  if (!index || list.length === 0) return;
  let current = true;
  reports = undefined;
  reportError = undefined;
  missing = 0;
  Promise.allSettled(
    list.map((r) => {
      let p = cache.get(r.path);
      if (!p) {
        p = loadReport(base, r);
        cache.set(r.path, p);
        p.catch(() => cache.delete(r.path));
      }
      return p.then((data) => [r.commit, data] as const);
    }),
  ).then((settled) => {
    if (!current) return;
    const pairs = settled.flatMap((s) => (s.status === "fulfilled" ? [s.value] : []));
    const failed = settled.flatMap((s) => (s.status === "rejected" ? [String(s.reason)] : []));
    missing = failed.length;
    if (pairs.length === 0) reportError = failed[0] ?? "no reports";
    else reports = new Map(pairs);
  });
  return () => {
    current = false;
  };
});

const shown = $derived<Line[]>(
  index && bench && measureId && reports ? linesOf(index, bench, params, measureId, reports) : [],
);
const changes = $derived(index && measureId && machine ? changesFor(index, shown, measureId, machine.id) : []);
const paramText = $derived(
  bench ? bench.params.map((a, i) => `${a.name} ${paramLabels(bench, params)[i]}`).join(", ") : "",
);
const commits = $derived(index && bench ? index.commits.filter((c) => c.group === bench.group) : []);
const label = (id: string) => commitName(index?.commits.find((x) => x.id === id) ?? { id });
const short = (caseId: string) => shown.find((l) => l.case === caseId)?.short ?? caseId;
const latest = $derived(index ? latestChanges(index) : []);
const exported = $derived(index?.changes !== undefined);
const worse = $derived(latest.filter((r) => r.way === "worse").length);
const HINTS: Record<ContractError["kind"], string> = {
  missing: "Check that index.json is in the data folder this site was built with, then reload.",
  version: "The data is in a newer or older format than this page reads: rebuild the site, or export the data again.",
  invalid:
    "The data does not have the shape the schema gives: export it again with the exporter that matches this site.",
};
const unit = $derived(measure?.unit ?? "");
let tableOpen = $state(false);
const tableRows = $derived.by(() => {
  const byCommit = shown.map((l) => new Map(l.points.map((p) => [p.commit, p])));
  return commits.map((c) => ({ c, cells: byCommit.map((m) => m.get(c.id)) })).filter((r) => r.cells.some((x) => x));
});
const filename = $derived(
  bench ? `${bench.name}-${params.map((p) => p.replace(/[^\w.-]+/g, "")).join("-")}`.replace(/-+$/, "") : "chart",
);
const title = $derived(bench ? `${bench.name}${paramText ? ` (${paramText})` : ""}` : "");

function setParam(i: number, value: string) {
  if (!bench) return;
  const labels = paramLabels(bench, params);
  labels[i] = value;
  go({ ...view, params: labels });
}

$effect(() => {
  const name = index?.project.name ?? "Benchmarks";
  document.title = bench ? `${bench.name} · ${name}` : name;
});
</script>

<a class="skip" href="#main">Skip to the results</a>
<header class="top">
  <div class="top-inner">
    <h1><a href={location.pathname} onclick={(e) => follow(e, { params: [] })}>{index?.project.name ?? "Benchmarks"}</a></h1>
    {#if index?.project.description}<p>{index.project.description}</p>{/if}
    {#if index?.project.links?.length}
      <nav aria-label="Project">
        {#each index.project.links as link (link.url)}<a href={link.url}>{link.name}</a>{/each}
        {#if index.project.url}<a href={index.project.url}>Source</a>{/if}
      </nav>
    {/if}
  </div>
</header>

<div class="frame">
  {#if error}
    <main class="view" id="main" tabindex="-1">
      <div class="empty" role="alert">
        <p><strong>The benchmark data did not load.</strong></p>
        <p class="mono">{error}</p>
        <p>{HINTS[errorKind]}</p>
      </div>
    </main>
  {:else if !index}
    <main class="view" id="main" tabindex="-1" aria-busy="true">
      <p aria-live="polite">Loading the benchmarks…</p>
      <div class="skeleton"></div>
    </main>
  {:else}
    <nav class="rail" aria-label="Benchmarks">
      <details open={wide}>
        <summary>{bench ? "All benchmarks" : "Benchmarks"}</summary>
        <a class="home" href={location.pathname} aria-current={bench ? undefined : "page"} onclick={(e) => follow(e, { params: [] })}
          >Latest changes</a
        >
        {#each index.groups as g (g.id)}
          <h2 id="rail-{g.id}">{g.name}</h2>
          <ul aria-labelledby="rail-{g.id}">
            {#each index.benchmarks.filter((b) => b.group === g.id) as b (b.id)}
              {@const next = { bench: b.id, params: [] }}
              <li>
                <a
                  href={writeView(next)}
                  aria-current={b.id === bench?.id ? "page" : undefined}
                  onclick={(e) => follow(e, next)}
                  >{#each breakable(b.name) as part, k (k)}{part}<wbr />{/each}</a
                >
              </li>
            {/each}
          </ul>
        {/each}
      </details>
    </nav>

    <main class="view" id="main" tabindex="-1">
      {#if !bench}
        <header>
          <h2>What moved in the latest releases</h2>
          <p class="lede">
            Each case compared between its package's last two releases. A move counts only when it is larger than that
            case's measured noise, which the exporter worked out from each run's spread.
          </p>
        </header>
        {#if !exported}
          <p class="empty">Changes were not exported with this data, so there is nothing to compare here.</p>
        {:else if latest.length === 0}
          <p class="empty">Nothing moved beyond its noise in any package's latest release.</p>
        {:else}
          <!-- svelte-ignore a11y_no_noninteractive_tabindex: a scrolling region must take focus to scroll by keyboard -->
          <div class="scroll gap" role="region" aria-label="Latest changes" tabindex="0">
            <table>
              <caption>
                {worse} worse, {latest.length - worse} better, beyond their noise; worse first, then the largest change.
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
                {#each latest as row, i (i)}
                  {@const next = { bench: row.bench.id, params: row.params, measure: row.change.measure }}
                  <tr>
                    <th scope="row" class="wrap">
                      <span class="quiet">{row.group.name}</span><br />
                      <a href={writeView(next)} onclick={(e) => follow(e, next)}
                        >{#each breakable(row.bench.name) as part, k (k)}{part}<wbr />{/each}</a
                      >
                      {#if row.params.length}<br /><span class="quiet">{row.params.join(", ")}</span>{/if}
                    </th>
                    <td class="num">
                      <span class={row.way}>{percent(row.change.ratio)} {row.way}</span><br />
                      <span class="quiet">noise {noiseText(row.change)}</span>
                    </td>
                    <td class="wrap">{row.env}</td>
                    <td class="nowrap">{row.from} → {row.to}</td>
                  </tr>
                {/each}
              </tbody>
            </table>
          </div>
        {/if}
      {:else}
        <header>
          <h2>{#each breakable(bench.name) as part, k (k)}{part}<wbr />{/each}</h2>
          <p>
            {#if group?.url}<a href={group.url}>{group.name}</a>{:else}{group?.name}{/if}
            · {measure?.name ?? measureId}{measure?.statistic ? `, ${measure.statistic}` : ""}{measure?.better
              ? `, ${measure.better} is better`
              : ""}
          </p>
        </header>

        <div class="controls">
          {#each bench.params as axis, i (axis.name)}
            {@const labels = axisLabels(bench)[i] ?? []}
            {#if labels.length === 1}
              <div class="field">
                <span class="label">{axis.name}</span>
                <span class="fixed">{labels[0]}</span>
              </div>
            {:else}
              <div class="field">
                <label for="axis-{i}">{axis.name}</label>
                <select
                  id="axis-{i}"
                  value={paramLabels(bench, params)[i]}
                  onchange={(e) => setParam(i, e.currentTarget.value)}
                >
                  {#each labels as l (l)}<option>{l}</option>{/each}
                </select>
              </div>
            {/if}
          {/each}
          {#if bench.measures.length > 1}
            <div class="field">
              <label for="measure">Measure</label>
              <select id="measure" value={measureId} onchange={(e) => go({ ...view, measure: e.currentTarget.value })}>
                {#each bench.measures as m (m)}<option value={m}>{index.measures.find((x) => x.id === m)?.name ?? m}</option>{/each}
              </select>
            </div>
          {/if}
          {#if machines.length > 1}
            <div class="field">
              <label for="machine">Machine</label>
              <select id="machine" value={machine?.id} onchange={(e) => go({ ...view, machine: e.currentTarget.value })}>
                {#each machines as m (m.id)}<option value={m.id}>{m.name}</option>{/each}
              </select>
            </div>
          {/if}
        </div>

        {#if reportError}
          <div class="empty" role="alert"><p>The results for this benchmark did not load: {reportError}</p></div>
        {:else if !reports}
          <div class="skeleton" aria-busy="true"><span class="sr">Loading the results…</span></div>
        {:else if shown.length === 0}
          <p class="empty">
            No results for these parameters on {machine?.name}. Every run at this setting failed or was skipped; try another
            value above.
          </p>
        {:else}
          {#if missing > 0}
            <p class="empty" role="status">
              {missing} of {wanted.length} reports did not load, so their releases are missing below.
            </p>
          {/if}
          <figure>
            {#await chart()}
              <div class="skeleton" aria-busy="true"><span class="sr">Loading the chart…</span></div>
            {:then { default: HistoryChart }}
              <HistoryChart lines={shown} {changes} {unit} better={measure?.better} {title} {filename} />
            {:catch reason}
              <div class="empty" role="alert"><p>The chart did not load: {String(reason)}</p></div>
            {/await}
            <figcaption>
              {measure?.name ?? "Value"} per release on {machine?.name}, one line per environment{measure?.bounds
                ? `; shaded: ${measure.bounds}`
                : ""}.
              A ring marks a release that moved beyond the case's noise (red worse, green better); a dashed line marks a
              level shift that Apache Otava found along the series.
            </figcaption>
          </figure>

          <h3 id="changes-h">Changes</h3>
          {#if !exported}
            <p class="quiet">Changes were not exported with this data.</p>
          {:else if changes.length === 0}
            <p class="quiet">Nothing moved beyond its noise here.</p>
          {:else}
            <!-- svelte-ignore a11y_no_noninteractive_tabindex: a scrolling region must take focus to scroll by keyboard -->
            <div class="scroll" role="region" aria-label="Changes" tabindex="0">
              <table aria-labelledby="changes-h">
                <thead>
                  <tr>
                    <th scope="col">Release</th>
                    <th scope="col" class="num">Change</th>
                    <th scope="col">Environment</th>
                    <th scope="col">Evidence</th>
                  </tr>
                </thead>
                <tbody>
                  {#each changes as c, i (i)}
                    {@const way = verdict(c.ratio, measure?.better)}
                    <tr>
                      <th scope="row" class="nowrap">{label(c.baseline)} → {label(c.commit)}</th>
                      <td class="num {way}">{percent(c.ratio)} {way}</td>
                      <td class="wrap">{short(c.case)}</td>
                      <td class="nowrap">
                        {c.method === "release" ? `release vs. noise ${noiseText(c)}` : `level shift (Otava), ${pText(c.pvalue)}`}
                      </td>
                    </tr>
                  {/each}
                </tbody>
              </table>
            </div>
          {/if}

          <details class="data" bind:open={tableOpen}>
            <summary>Data table: {tableRows.length} releases × {shown.length} environments</summary>
            {#if tableOpen}<!-- built on opening: a large table is slow to render -->
            <!-- svelte-ignore a11y_no_noninteractive_tabindex: a scrolling region must take focus to scroll by keyboard -->
            <div class="scroll" role="region" aria-label="Data table" tabindex="0">
              <table>
                <caption>
                  {title}, {measure?.name ?? ""} on {machine?.name}.{measure?.bounds ? ` Range: ${measure.bounds}.` : ""}
                </caption>
                <thead>
                  <tr>
                    <th scope="col">Release</th>
                    <th scope="col">Date</th>
                    {#each shown as l (l.case)}<th scope="col" class="num" title={l.name}>{l.short}</th>{/each}
                  </tr>
                </thead>
                <tbody>
                  {#each tableRows as row (row.c.id)}
                    <tr>
                      <th scope="row">{commitName(row.c)}</th>
                      <td class="nowrap">{row.c.date.slice(0, 10)}</td>
                      {#each row.cells as p, j (j)}
                        <td class="num">
                          {#if p}
                            {format(p.value, unit)}
                            {#if p.lower !== undefined && p.upper !== undefined}
                              <br /><span class="quiet">{format(p.lower, unit)} to {format(p.upper, unit)}</span>
                            {/if}
                          {:else}<span class="quiet">none</span>{/if}
                        </td>
                      {/each}
                    </tr>
                  {/each}
                </tbody>
              </table>
            </div>
            <dl class="envs">
              {#each shown as l (l.case)}
                {#if l.short !== l.name}<dt>{l.short}</dt><dd class="mono">{l.name}</dd>{/if}
              {/each}
            </dl>
            {/if}
          </details>
        {/if}
      {/if}
    </main>
  {/if}
</div>
