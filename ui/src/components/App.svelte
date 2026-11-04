<script lang="ts">
import { tick } from "svelte";
import {
  type BenchmarkIndex,
  type BenchmarkReport,
  type Change,
  ContractError,
  type Guidance,
  loadGuidance,
  loadIndex,
  loadReport,
  type Report,
} from "../lib/contract";
import {
  axisLabels,
  benchmarkLabel,
  breakable,
  changesFor,
  commitName,
  findBench,
  format,
  type Line,
  lines as linesOf,
  noiseText,
  pageOf,
  paramLabels,
  percent,
  pickParams,
  pText,
  readView,
  type View,
  verdict,
  writeView,
} from "../lib/history";
import Findings from "./Findings.svelte";
import LogoMark from "./LogoMark.svelte";
import ReleaseChanges from "./ReleaseChanges.svelte";
import SetupHome from "./SetupHome.svelte";

type Axis = BenchmarkIndex["benchmarks"][number]["params"][number];

let {
  base,
  build,
  about = "/about/",
  story = "/stories/solver-choice/",
}: { base: string; build?: { label: string; url: string }; about?: string; story?: string } = $props();

// Fetched with the first chart, so the start page does not load Plot.
let chartModule: Promise<typeof import("./HistoryChart.svelte")> | undefined;
const chart = () => (chartModule ??= import("./HistoryChart.svelte"));

let index = $state<BenchmarkIndex>();
let error = $state<string>();
let guidance = $state<Guidance>();
let guidanceReady = $state(false);
let guidanceError = $state<string>();
let errorKind = $state<ContractError["kind"]>("invalid");
let view = $state<View>(readView(location.search, location.hash));
let reports = $state<Map<string, BenchmarkReport>>();
let reportError = $state<string>();
let missing = $state(0); // reports that did not load; the chart draws the rest
const cache = new Map<string, Promise<BenchmarkReport>>();
// The rail is a disclosure on a phone and always open beside the view on a wide screen.
const PAGES = [
  ["home", "Setup"],
  ["explorer", "Benchmarks"],
] as const;
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
  loadGuidance(base)
    .then(
      (data) => {
        guidance = data;
      },
      (reason: unknown) => {
        guidanceError = String(reason);
      },
    )
    .finally(() => {
      guidanceReady = true;
    });
  const back = () => {
    view = readView(location.search, location.hash);
  };
  addEventListener("popstate", back);
  addEventListener("hashchange", back);
  return () => {
    removeEventListener("popstate", back);
    removeEventListener("hashchange", back);
  };
});

/** Show NEXT, and keep it in the URL; a new benchmark is a new history entry, a new setting is not. */
function go(next: View, focusPage = true) {
  const moved = pageOf(next) !== pageOf(view);
  const push = next.bench !== view.bench || moved || next.platform !== view.platform || next.check !== view.check;
  view = next;
  const url = writeView(next) || location.pathname;
  if (push) history.pushState(null, "", url);
  else history.replaceState(null, "", url);
  if (push) scrollTo({ top: 0 });
  // The link that led here may be gone, so start keyboard focus at the new page.
  if (moved && focusPage) tick().then(() => document.getElementById("main")?.focus({ preventScroll: true }));
}

function follow(e: MouseEvent, next: View) {
  if (e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;
  e.preventDefault();
  go(next);
}

const page = $derived(pageOf(view));
// Without a benchmark, Benchmarks opens on its overview: the findings and the latest release changes.
const bench = $derived(index && findBench(index, view));
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
function fetched(r: Report): Promise<BenchmarkReport> {
  let p = cache.get(r.path);
  if (!p) {
    p = loadReport(base, r);
    cache.set(r.path, p);
    p.catch(() => cache.delete(r.path));
  }
  return p;
}

// The overview draws each change's history: every report of a group with a change (28 KB gzipped in all).
let overview = $state(new Map<string, BenchmarkReport>());
const requested = new Set<string>();
$effect(() => {
  if (!index || page !== "explorer" || bench) return;
  const cases = new Map(index.cases.map((c) => [c.id, c.benchmark]));
  const moved = new Set((index.changes ?? []).map((c) => cases.get(c.case)));
  const groups = new Set(index.benchmarks.filter((b) => moved.has(b.id)).map((b) => b.group));
  for (const r of index.reports.filter((x) => groups.has(x.group) && !requested.has(x.path))) {
    requested.add(r.path);
    fetched(r).then(
      (data) => {
        overview = new Map(overview).set(r.path, data);
      },
      () => {}, // a missing report leaves its rows without a line
    );
  }
});

$effect(() => {
  const list = wanted;
  if (!index || list.length === 0) return;
  let current = true;
  reports = undefined;
  reportError = undefined;
  missing = 0;
  Promise.allSettled(list.map((r) => fetched(r).then((data) => [r.commit, data] as const))).then((settled) => {
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
// Each linked solver once: "UMFPACK" and "UMFPACK, MKL" share a page.
const solverLinks = $derived.by(() => {
  const envs = new Map(index?.environments.map((e) => [e.id, e]));
  const out = new Map<string, string>();
  for (const l of shown) {
    const env = envs.get(l.env);
    if (env?.url && !out.has(env.url)) out.set(env.url, (env.label ?? env.name).split(/,| on | · /)[0] ?? env.name);
  }
  return [...out].map(([url, label]) => ({ url, label }));
});
// Commits on the chart that are not releases: release changes skip them.
const unreleased = $derived(
  new Set(shown.flatMap((l) => l.points.filter((p) => !p.released).map((p) => p.commit))).size,
);
const paramText = $derived(
  bench ? bench.params.map((a, i) => `${a.name} ${paramLabels(bench, params)[i]}`).join(", ") : "",
);
const commits = $derived(index && bench ? index.commits.filter((c) => c.group === bench.group) : []);
const label = (id: string) => commitName(index?.commits.find((x) => x.id === id) ?? { id });
const short = (caseId: string) => shown.find((l) => l.case === caseId)?.short ?? caseId;
const exported = $derived(index?.changes !== undefined);
// One row per environment and release: the release check and Otava often find the same move.
const changeRows = $derived.by(() => {
  const by = new Map<string, Change[]>();
  for (const c of changes) by.set(`${c.case}/${c.commit}`, [...(by.get(`${c.case}/${c.commit}`) ?? []), c]);
  return [...by.values()].flatMap((all) => {
    const lead = all.find((c) => c.method === "release") ?? all[0];
    return lead ? [{ lead, all }] : [];
  });
});

const HINTS: Record<ContractError["kind"], string> = {
  missing: "Check that index.json is in the data folder, then reload.",
  version: "The data uses a newer or older format. Rebuild the site or export it again.",
  invalid: "Export the data again with the matching exporter.",
};
const unit = $derived(measure?.unit ?? "");
let tableOpen = $state(false);
let search = $state("");
// The masthead's search shows its matches in the catalogue; Enter opens the first.
function searchFor(text: string) {
  search = text;
  if (page !== "explorer" || bench) go({ page: "explorer", params: [] }, false);
}
function openFirst(e: SubmitEvent) {
  e.preventDefault();
  const first = matching[0];
  if (first) go({ bench: first.id, params: [] });
}
const matching = $derived(
  index?.benchmarks.filter((b) => `${b.name} ${benchmarkLabel(b.name)}`.toLowerCase().includes(search.toLowerCase())) ??
    [],
);
function labelOf(b: BenchmarkIndex["benchmarks"][number]): string {
  const text = benchmarkLabel(b.name);
  const collisions = index?.benchmarks.filter(
    (other) => other.group === b.group && benchmarkLabel(other.name) === text,
  );
  return collisions && collisions.length > 1 ? `${text} (${b.name})` : text;
}
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
  go({ ...view, bench: bench.id, params: labels });
}

// On a phone the masthead scrolls sideways; keep the current page's link in view (32px clears the fade).
let masthead = $state<HTMLElement>();
$effect(() => {
  const link = page && masthead?.querySelector('[aria-current="page"]');
  if (!masthead || !link) return;
  const over = link.getBoundingClientRect().right - masthead.getBoundingClientRect().right + 32;
  if (over > 0) masthead.scrollLeft += over;
});

$effect(() => {
  const name = index?.project.name ?? "Benchmarks";
  document.title = bench
    ? `${labelOf(bench)} · ${name}`
    : `${{ home: "Setup", explorer: "Benchmarks" }[page]} · ${name}`;
});
</script>

{#snippet parameterNote(axis: Axis, i: number)}
  {@const value = bench ? paramLabels(bench, params)[i] ?? "" : ""}
  {@const at = (axis.labels ?? axis.values).indexOf(value)}
  {@const note = axis.notes?.[at]}
  {@const link = axis.links?.[at]}
  {axis.description}{#if note}{" "}{#if link && axis.values.length > 1}<a href={link}>{value}</a>{:else}<strong>{value}</strong>{/if}: {note}{/if}
{/snippet}

<a class="skip" href="#main">Skip to the results</a>
<header class="top">
  <div class="top-inner">
    <h1><a href={location.pathname} onclick={(e) => follow(e, { params: [] })}><LogoMark size={24} /><span>{index?.project.name === "brightway-benchmarks" ? "Brightway Benchmarks" : (index?.project.name ?? "Brightway Benchmarks")}</span></a></h1>
    <nav class="primary-nav" aria-label="Main" bind:this={masthead}>
      {#each PAGES as [id, text] (id)}
        <a href={writeView({page:id,params:[]})} aria-current={page === id ? "page" : undefined} onclick={(e) => follow(e, {page:id,params:[]})}>{text}</a>
      {/each}
    </nav>
    <form class="masthead-search" role="search" onsubmit={openFirst}>
      <label class="sr" for="benchmark-search">Find a benchmark</label>
      <input id="benchmark-search" type="search" value={search} oninput={(e) => searchFor(e.currentTarget.value)} placeholder="Find a benchmark…" />
    </form>
    <button type="button" class="theme-toggle" data-theme-toggle aria-label="Switch to dark theme" title="Switch to dark theme">
      <svg data-theme-icon="moon" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M20.8 13A9 9 0 0 1 11 3.2 9 9 0 1 0 20.8 13Z"/></svg>
      <svg data-theme-icon="sun" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" aria-hidden="true"><circle cx="12" cy="12" r="4"/><path d="M12 2v2m0 16v2M2 12h2m16 0h2M5 5l1.5 1.5m11 11L19 19M5 19l1.5-1.5m11-11L19 5"/></svg>
    </button>
  </div>
</header>

<div class="frame" class:fullwidth={page !== "explorer"}>
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
    {#if page === "explorer"}
    <nav class="rail" aria-label="Benchmarks">
      <details open={wide || search.length > 0}>
        <summary>Benchmark catalogue</summary>
        <a class="home" href={writeView({page:"explorer",params:[]})} aria-current={bench ? undefined : "page"} onclick={(e) => follow(e, { page:"explorer", params: [] })}
          >All benchmarks</a
        >
        {#if matching.length === 0}<p class="rail-empty">No benchmarks match “{search}”.</p>{/if}
        {#each index.groups.filter((g) => matching.some((b) => b.group === g.id)) as g (g.id)}
          <h2 id="rail-{g.id}">{g.name}</h2>
          <ul aria-labelledby="rail-{g.id}">
            {#each matching.filter((b) => b.group === g.id) as b (b.id)}
              {@const next = { bench: b.id, params: [] }}
              <li>
                <a
                  href={writeView(next)}
                  aria-current={b.id === bench?.id ? "page" : undefined}
                  onclick={(e) => follow(e, next)}
                  title={b.name}
                  >{labelOf(b)}</a
                >
              </li>
            {/each}
          </ul>
        {/each}
      </details>
    </nav>
    {/if}

    <main class="view" id="main" tabindex="-1">
      {#if guidanceError && page === "home"}<p class="empty" role="status">Setup guidance could not be loaded. Benchmark histories remain available. {guidanceError}</p>{/if}
      {#if page === "home"}
        <SetupHome {guidance} ready={guidanceReady} {index} {view} {go} {follow} {story} />
      {:else if !bench}
        {#if view.bench}<p class="empty" role="status">This benchmark is not in the current data. Choose one from the catalogue.</p>{/if}
        <header class="overview-intro"><h2>Benchmarks</h2><p class="lede">How fast each Brightway release runs everyday LCA calculations. Choose a finding, a change or a benchmark from the catalogue for its history.</p><p class="lede"><a href={story}>The same LCA takes 2.6 s or 28 s depending on one install choice</a>: the story behind the solver numbers.</p></header>
        <Findings {index} {follow} wide />
        <ReleaseChanges {index} {view} {go} {follow} loaded={overview} />

      {:else}
        <header class="bench-header">
          <h2>{labelOf(bench)}</h2>
          {#if bench.description}<p class="bench-about">{bench.description}</p>{/if}
          <p class="bench-meta">
            {#if group?.url}<a href={group.url}>{group.name}</a>{:else}{group?.name}{/if}
            · {measure?.name ?? measureId}{measure?.statistic ? `, ${measure.statistic}` : ""}{measure?.better
              ? `, ${measure.better} is better`
              : ""}
            · <code class="benchmark-id">{#if bench.url}<a href={bench.url} title="Its source: how it is measured">{#each breakable(bench.name) as part, k (k)}{part}<wbr />{/each}</a>{:else}{#each breakable(bench.name) as part, k (k)}{part}<wbr />{/each}{/if}</code>
          </p>
          {#if group?.links?.length || bench.codspeed}
            <p class="bench-meta">
              {#each group?.links ?? [] as l, k (l.name)}{#if k}{" · "}{/if}<a href={l.url}>{l.name}</a>{/each}{#if bench.codspeed}{#if group?.links?.length}{" · "}{/if}<a href={bench.codspeed} title="Instruction counts for the current release at smoke size">CodSpeed</a>{/if}
            </p>
          {/if}
        </header>

        <div class="controls">
          {#each bench.params as axis, i (axis.name)}
            {@const labels = axisLabels(bench)[i] ?? []}
            {@const value = paramLabels(bench, params)[i] ?? ""}
            {@const at = labels.indexOf(value)}
            {@const note = axis.notes?.[at]}
            {@const link = axis.links?.[at]}
            <div class="field">
              {#if labels.length === 1}
                <span class="label">{axis.name}</span>
                <span class="fixed">{#if link}<a href={link}>{value}</a>{:else}{value}{/if}</span>
              {:else}
                <label for="axis-{i}">{axis.name}</label>
                <select id="axis-{i}" value={value} onchange={(e) => setParam(i, e.currentTarget.value)}>
                  {#each labels as l (l)}<option>{l}</option>{/each}
                </select>
              {/if}
              {#if axis.description || note}
                <p class="field-note parameter-inline">{@render parameterNote(axis, i)}</p>
              {/if}
            </div>
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

        {#if bench.params.some((axis) => axis.description || axis.notes?.some(Boolean))}
          <details class="parameter-details">
            <summary>Parameter details</summary>
            <dl>{#each bench.params as axis, i (axis.name)}<dt>{axis.name}</dt><dd class="field-note">{@render parameterNote(axis, i)}</dd>{/each}</dl>
          </details>
        {/if}

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
              {measure?.name ?? "Value"} per release on {machine?.name}, one line per environment and one even step per commit,
              not by date{measure?.bounds ? `; the band is ${measure.bounds}` : ""}. A ring marks a change beyond its noise (red worse,
              teal better); a dashed line marks a level shift across the whole series.
              {#if solverLinks.length}<span class="env-links">About the environments: {#each solverLinks as l, k (l.url)}{#if k}{" · "}{/if}<a href={l.url}>{l.label}</a>{/each}.</span>{/if}
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
              <table class="responsive-table" aria-labelledby="changes-h">
                <thead>
                  <tr>
                    <th scope="col">Release</th>
                    <th scope="col" class="num">Change</th>
                    <th scope="col">Environment</th>
                    <th scope="col">Evidence</th>
                  </tr>
                </thead>
                <tbody>
                  {#each changeRows as row, i (i)}
                    {@const c = row.lead}
                    {@const way = verdict(c.ratio, measure?.better)}
                    <tr>
                      <th scope="row" class="nowrap">{label(c.baseline)} → {label(c.commit)}</th>
                      <td class="num {way}" data-label="Change">{percent(c.ratio)} {way}</td>
                      <td class="wrap" data-label="Environment">{short(c.case)}</td>
                      <td class="nowrap" data-label="Evidence">
                        {row.all
                          .map((e) => (e.method === "release" ? `beyond ${noiseText(e)} noise` : `level shift in the series, ${pText(e.pvalue)}`))
                          .join("; ")}
                      </td>
                    </tr>
                  {/each}
                </tbody>
              </table>
            </div>
          {/if}
          {#if exported && unreleased > 0}
            <p class="quiet">
              {unreleased === 1 ? "One commit" : `${unreleased} commits`} on this chart {unreleased === 1 ? "is" : "are"} not a
              release and {unreleased === 1 ? "is" : "are"} drawn faint; release changes compare releases only, so a move there
              shows only if it shifts the whole series.
            </p>
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

<footer class="site-footer">
  <nav aria-label="Project">
    {#each index?.project.links ?? [] as link (link.url)}<a href={link.url}>{link.name}</a>{/each}
    {#if index?.project.url}<a href={index.project.url}>GitHub</a>{/if}
    <a href={story}>Solver story</a>
    <a href={about}>About &amp; privacy</a>
    {#if build}<a class="build-version" href={build.url} aria-label="Build {build.label}">{build.label}</a>{/if}
  </nav>
</footer>
