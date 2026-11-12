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
import { envNotes, solverLinks } from "../lib/environments";
import {
  axisLabels,
  benchLabel,
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
  seriesSlots,
  type View,
  verdict,
  writeView,
} from "../lib/history";
import { staticHref, VIEWER_PAGES } from "../lib/pages";
import { scrollable } from "../lib/scrollable";
import Masthead from "./Masthead.svelte";
import PythonSupport from "./PythonSupport.svelte";
import ReleaseChanges from "./ReleaseChanges.svelte";
import SetupHome from "./SetupHome.svelte";
import SolverComparison from "./SolverComparison.svelte";

type Axis = BenchmarkIndex["benchmarks"][number]["params"][number];

let {
  base,
  build,
  home = "/",
}: {
  base: string;
  build?: { label: string; url: string };
  /** The site's root, where the static pages live. */
  home?: string;
} = $props();
const story = $derived(staticHref(home, "solver-choice"));
// A link such as Setup's "All Python versions" names a section of the overview, which draws after the data loads.
$effect(() => {
  if (view.page === "explorer" && !view.bench && index && guidance && location.hash)
    tick().then(() => document.getElementById(location.hash.slice(1))?.scrollIntoView());
});
const findingsPage = $derived(staticHref(home, "findings"));

// Fetched once a benchmark is chosen, so the start page does not load Plot. A failed fetch is forgotten,
// so the next benchmark tries again: after a deploy the old chunk is gone and only a reload finds the new one.
let chartModule: Promise<typeof import("./HistoryChart.svelte")> | undefined;
function chart() {
  chartModule ??= import("./HistoryChart.svelte");
  chartModule.catch(() => {
    chartModule = undefined;
  });
  return chartModule;
}

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
function go({ q: _handedOver, ...next }: View, focusPage = true) {
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
// The chart's code loads beside the benchmark's reports, not after them.
$effect(() => {
  if (view.bench) chart();
});
// Without a benchmark, Benchmarks opens on its overview: the findings and the latest release changes.
const bench = $derived(index && findBench(index, view));
const group = $derived(bench && index?.groups.find((g) => g.id === bench.group));
const params = $derived(bench ? pickParams(bench, view.params) : []);
// The findings this view shows: same benchmark, and every value the finding fixes is the one chosen.
const shownFindings = $derived(
  bench
    ? (index?.findings ?? []).filter(
        (f) => f.benchmark === bench.id && pickParams(bench, f.params).every((v, i) => !f.params[i] || v === params[i]),
      )
    : [],
);
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
const slots = $derived(index ? seriesSlots(index, shown) : []);
const changes = $derived(index && measureId && machine ? changesFor(index, shown, measureId, machine.id) : []);
const notes = $derived(envNotes(index, shown));
const solvers = $derived(solverLinks(index, shown, notes));
// Commits on the chart that are not releases: release changes skip them.
const unreleased = $derived(
  new Set(shown.flatMap((l) => l.points.filter((p) => !p.released).map((p) => p.commit))).size,
);
const paramText = $derived(
  bench ? bench.params.map((a, i) => `${a.label ?? a.name} ${paramLabels(bench, params)[i]}`).join(", ") : "",
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
// Opened from a static page's search, which hands its words over as ?q=.
const handedOver = readView(location.search).q ?? "";
let search = $state(handedOver);
// On a phone the search sits behind an icon in the masthead.
let searchOpen = $state(handedOver.length > 0);
function toggleSearch() {
  searchOpen = !searchOpen;
  if (searchOpen) tick().then(() => document.getElementById("benchmark-search")?.focus());
}
// The masthead's search lists benchmarks and the static pages' sections as you type; Enter opens the first.
function openFirst(e: SubmitEvent) {
  e.preventDefault();
  const first = matching[0];
  if (first) go({ bench: first.id, params: [] });
  // No benchmark matches: open the first page hit for these words, once Pagefind has them.
  else enterFor = search.trim();
}
let enterFor = $state("");
$effect(() => {
  if (!enterFor) return;
  // Typing on cancels the pending Enter.
  if (enterFor !== search.trim()) enterFor = "";
  else if (pagesSettled) {
    enterFor = "";
    if (pageResult.hits[0]) location.href = pageResult.hits[0].url;
  }
});
// Every word must appear in the benchmark's name, label or package, in any order.
const matching = $derived.by(() => {
  const words = search.toLowerCase().split(/\s+/).filter(Boolean);
  return (
    index?.benchmarks.filter((b) => {
      const g = groupOf(b);
      const text = `${b.name} ${labelOf(b)} ${g?.label ?? ""} ${g?.name ?? ""}`.toLowerCase();
      return words.every((w) => text.includes(w));
    }) ?? []
  );
});

// Findings, stories and About are indexed by Pagefind after the build (`pnpm build`); `pnpm dev` has no
// index, so the search lists benchmarks only there.
interface Pagefind {
  options(o: { baseUrl: string }): Promise<void>;
  debouncedSearch(text: string): Promise<{ results: { data(): Promise<PageData> }[] } | null>;
}
interface PageSection {
  url: string;
  title: string;
  excerpt: string;
}
interface PageData extends PageSection {
  meta: { title: string };
  sub_results: PageSection[];
}
let pagefind: Promise<Pagefind | undefined> | undefined;
// A runtime URL: the bundler must not look for Pagefind, which is written after it runs.
const loadPagefind = (url: string): Promise<Pagefind> => import(/* @vite-ignore */ url);
// The hits name the words they answer. While Pagefind works on new words the last hits stay in view, marked busy,
// but Enter and the status line wait for the answer.
let pageResult = $state<{ text: string; hits: (PageSection & { page: string })[] }>({ text: "", hits: [] });
const pagesSettled = $derived(pageResult.text === search.trim());
$effect(() => {
  const text = search.trim();
  if (!text) return;
  pagefind ??= loadPagefind(`${import.meta.env.BASE_URL}pagefind/pagefind.js`)
    .then(async (pf) => {
      await pf.options({ baseUrl: home });
      return pf;
    })
    .catch(() => undefined);
  let stale = false;
  pagefind.then(async (pf) => {
    let hits: typeof pageResult.hits = [];
    // Without an index (`pnpm dev`) or after a failed fetch, the pages have nothing to add.
    try {
      const found = pf ? await pf.debouncedSearch(text) : { results: [] };
      if (!found) return; // superseded by newer words
      const pages = await Promise.all(found.results.slice(0, 5).map((r) => r.data()));
      // A page's best sections, not the page itself, when it has headings to land on.
      hits = pages
        .flatMap((d) =>
          (d.sub_results.length ? d.sub_results.slice(0, 3) : [d]).map((x) => ({ ...x, page: d.meta.title })),
        )
        .slice(0, 6);
    } catch {}
    if (!stale) pageResult = { text, hits };
  });
  return () => {
    stale = true;
  };
});
// Opened from a static page's search: the words arrive in the field, with their results open.
$effect(() => {
  if (handedOver) document.getElementById("benchmark-search")?.focus();
});
const labelOf = (b: BenchmarkIndex["benchmarks"][number]) => (index ? benchLabel(index, b) : b.name);
const groupOf = (b: BenchmarkIndex["benchmarks"][number]) => index?.groups.find((g) => g.id === b.group);
// A name shared by several packages ("MultiLCA" in bw2calc and bw2calc (conda-forge)) says which one it is.
const repeated = $derived(
  new Set((index?.benchmarks ?? []).map(labelOf).filter((l, _, all) => all.indexOf(l) !== all.lastIndexOf(l))),
);
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

// The masthead's name for the site; the data's project name is its repository's.
const siteName = $derived(
  index?.project.name === "brightway-benchmarks"
    ? "Brightway Benchmarks"
    : (index?.project.name ?? "Brightway Benchmarks"),
);
$effect(() => {
  document.title = `${bench ? labelOf(bench) : { home: "Setup", explorer: "Benchmarks" }[page]} · ${siteName}`;
});
</script>

{#snippet parameterNote(axis: Axis, i: number)}
  {@const value = bench ? paramLabels(bench, params)[i] ?? "" : ""}
  {@const at = (axis.labels ?? axis.values).indexOf(value)}
  {@const note = axis.notes?.[at]}
  {@const link = axis.links?.[at]}
  {axis.description}{#if note}{" "}{#if link}<a href={link}>{value}</a>{:else}<strong>{value}</strong>{/if}: {note}{/if}
{/snippet}

{#snippet technical(detail: string, hint?: string)}
  <details class="technical"><summary>Technical details</summary><p class="mono">{detail}</p>{#if hint}<p>{hint}</p>{/if}</details>
{/snippet}

<a class="skip" href="#main">Skip to the results</a>
<Masthead
  name={siteName}
  home={location.pathname}
  links={[
    ...VIEWER_PAGES.map(({ id, text }) => ({
      href: writeView({ page: id, params: [] }),
      text,
      current: page === id,
      onclick: (e: MouseEvent) => follow(e, { page: id, params: [] }),
    })),
    { href: findingsPage, text: "Findings", current: false },
  ]}
  bind:nav={masthead}
  onbrand={(e) => follow(e, { params: [] })}
  search={{
    value: search,
    open: searchOpen,
    toggle: toggleSearch,
    input: (text: string) => (search = text),
    submit: openFirst,
    results: {
      benchmarks: matching.slice(0, 6).map((b) => {
        const next = { bench: b.id, params: [] };
        const g = groupOf(b);
        return { href: writeView(next), title: labelOf(b), detail: g?.label ?? g?.name ?? "", onclick: (e: MouseEvent) => follow(e, next) };
      }),
      more: matching.length > 6 ? { count: matching.length, href: writeView({ page: "explorer", params: [] }), onclick: (e: MouseEvent) => follow(e, { page: "explorer", params: [] }) } : undefined,
      pages: pageResult.hits.map((h) => ({ href: h.url, title: h.title, detail: h.page, excerpt: h.excerpt })),
      pending: !pagesSettled,
    },
  }}
/>

<div class="frame" class:fullwidth={page !== "explorer"}>
  {#if error}
    <main class="view" id="main" tabindex="-1">
      <div class="empty" role="alert">
        <p><strong>The results could not load.</strong> Reload the page, or try again later.</p>
        {@render technical(error, HINTS[errorKind])}
      </div>
    </main>
  {:else if !index}
    <main class="view" id="main" tabindex="-1" aria-busy="true">
      <p aria-live="polite">{page === "home" ? "Loading…" : "Loading the benchmarks…"}</p>
      <div class="skeleton"></div>
    </main>
  {:else}
    {#if page === "explorer"}
    <nav class="rail" aria-label="Benchmarks">
      <details class="rail-all" open={wide || search.length > 0}>
        <summary>Benchmark catalogue</summary>
        <a class="home" href={writeView({page:"explorer",params:[]})} aria-current={bench ? undefined : "page"} onclick={(e) => follow(e, { page:"explorer", params: [] })}
          >All benchmarks</a
        >
        <div class="rail-status" role="status">
          {#if search}
            {#if matching.length === 0}<p class="rail-empty">No benchmarks match “{search}”.</p>{:else}<p class="rail-found">{matching.length} {matching.length === 1 ? "benchmark" : "benchmarks"}</p>{/if}
          {/if}
        </div>
        {#each index.groups.filter((g) => matching.some((b) => b.group === g.id)) as g (g.id)}
          {@const members = matching.filter((b) => b.group === g.id)}
          <details class="rail-group" open={g.id === bench?.group || search.length > 0}>
            <summary>{g.label ?? g.name}{" "}<span class="rail-count">({members.length})</span></summary>
            {#if g.description}<p class="rail-about">{g.description}</p>{/if}
            <ul aria-label={g.label ?? g.name}>
              {#each members as b (b.id)}
                {@const next = { bench: b.id, params: [] }}
                <li>
                  <a
                    href={writeView(next)}
                    aria-current={b.id === bench?.id ? "page" : undefined}
                    onclick={(e) => follow(e, next)}
                    title={b.name}
                    >{labelOf(b)}{#if repeated.has(labelOf(b))}<span class="sr"> in {g.label ?? g.name}</span>{/if}</a
                  >
                </li>
              {/each}
            </ul>
          </details>
        {/each}
      </details>
    </nav>
    {/if}

    <main class="view" id="main" tabindex="-1">
      {#if guidanceError && page === "home"}<div class="empty" role="status"><p>Setup guidance could not be loaded. Benchmark histories remain available.</p>{@render technical(guidanceError)}</div>{/if}
      {#if page === "home"}
        <SetupHome {guidance} ready={guidanceReady} {index} {view} {go} {follow} name={siteName} findings={findingsPage} />
      {:else if !bench}
        {#if view.bench}<p class="empty" role="status">This benchmark is not in the current data. Choose one from the catalogue.</p>{/if}
        <header class="overview-intro"><h2>Benchmarks</h2><p class="lede">How fast each Brightway release runs everyday LCA calculations. Open a change or a benchmark from the catalogue for its history, or read <a href={findingsPage}>what the benchmarks found</a>.</p></header>
        {#if guidance?.solverComparison}<SolverComparison comparison={guidance.solverComparison} {story} />{/if}
        <ReleaseChanges {index} {view} {go} {follow} loaded={overview} />
        {#if guidance}<PythonSupport {guidance} /><PythonSupport {guidance} eol />{/if}

      {:else}
        <header class="bench-header">
          <h2>{labelOf(bench)}</h2>
          {#if bench.description}<p class="bench-about">{bench.description}</p>{/if}
          {#each shownFindings as f (f.title)}<p class="bench-finding"><strong>Finding:</strong> {f.title}.{#if f.url}{" "}<a href={f.url}>Read the write-up<span class="sr"> on {f.title}</span></a>{/if}</p>{/each}
          <p class="bench-meta">
            {#if group?.url}<a href={group.url}>{group.label ?? group.name}</a>{:else}{group?.label ?? group?.name}{/if}
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
            <div class="field">
              {#if labels.length === 1}
                <span class="label">{axis.label ?? axis.name}</span>
                <span class="fixed">{value}</span>
              {:else}
                <label for="axis-{i}">{axis.label ?? axis.name}</label>
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
            <dl>{#each bench.params as axis, i (axis.name)}<dt>{axis.label ?? axis.name}</dt><dd class="field-note">{@render parameterNote(axis, i)}</dd>{/each}</dl>
          </details>
        {/if}

        {#if reportError}
          <div class="empty" role="alert"><p>The results for this benchmark could not load. Reload the page, or try again later.</p>{@render technical(reportError)}</div>
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
          <figure aria-labelledby="reading-guide">
            {#await chart()}
              <div class="skeleton" aria-busy="true"><span class="sr">Loading the chart…</span></div>
            {:then { default: HistoryChart }}
              <HistoryChart lines={shown} {slots} {changes} {unit} better={measure?.better} {title} {filename} />
            {:catch reason}
              <div class="empty" role="alert"><p>The chart did not load. Reload the page.</p>{@render technical(String(reason))}</div>
            {/await}
            <figcaption>
              <p class="reading-guide" id="reading-guide">
                {measure?.name ?? "Value"} per release on {machine?.name}, one line per environment and one even step per commit,
                not by date{measure?.noise
                  ? `; the band is the noise allowance: ${measure.bounds ? `±${measure.noise.spreads} × the width of ${measure.bounds}, ` : ""}at least ±${+(measure.noise.floor * 100).toFixed(1)}%`
                  : measure?.bounds ? `; the band is ${measure.bounds}` : ""}. A ring marks a release that moved further than its band and the one before it allow (red worse,
                teal better); a dashed line marks a level shift across the whole series.
              </p>
              {#if notes.length}
                <dl class="env-notes">
                  {#each notes as note (`${note.name}|${note.text}`)}
                    <div><dt>{#if note.url}<a href={note.url}>{note.name}</a>{:else}{note.name}{/if}</dt><dd>{note.text}</dd></div>
                  {/each}
                </dl>
              {/if}
              {#if solvers.length}<p class="env-links">{notes.length ? "Also" : "About"} the environments: {#each solvers as l, k (l.url)}{#if k}{" · "}{/if}<a href={l.url}>{l.label}</a>{/each}.</p>{/if}
            </figcaption>
          </figure>

          <h3 id="changes-h">Changes</h3>
          {#if !exported}
            <p class="quiet">Changes were not exported with this data.</p>
          {:else if changes.length === 0}
            <p class="quiet">Nothing moved beyond its noise here.</p>
          {:else}
            <div class="scroll" role="region" aria-label="Changes" use:scrollable>
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
            <div class="scroll" role="region" aria-label="Data table" use:scrollable>
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
                            {#if p.noise !== undefined}<br /><span class="quiet">{noiseText({ threshold: p.noise })} noise</span>{/if}
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
    <a href={staticHref(home, "about")}>About & privacy</a>
    {#if build}<a class="build-version" href={build.url} aria-label="Build {build.label}">{build.label}</a>{/if}
  </nav>
  <p class="licence">© 2026 <a href="https://simonvanlierde.com/">Simon van Lierde</a> · <a href="https://github.com/simonvanlierde/brightway-benchmarks/blob/main/LICENSE">BSD 3-Clause</a></p>
</footer>
