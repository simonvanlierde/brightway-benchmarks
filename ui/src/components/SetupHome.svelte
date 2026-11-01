<script lang="ts">
import { tick } from "svelte";
import type { BenchmarkIndex, Guidance } from "../lib/contract";
import { checkKind, dateLabel, type GuidanceCheck, statusLabel, statusTone } from "../lib/guidance";
import { benchmarkLabel, format, latestChanges, noiseText, percent, type View, writeView } from "../lib/history";
import Findings from "./Findings.svelte";
import InstallSet from "./InstallSet.svelte";
import LogoMark from "./LogoMark.svelte";

let {
  guidance,
  ready,
  index,
  view,
  go,
  follow,
}: {
  guidance: Guidance | undefined;
  ready: boolean;
  index: BenchmarkIndex;
  view: View;
  go: (view: View) => void;
  follow: (event: MouseEvent, view: View) => void;
} = $props();
const chosen = $derived(guidance?.checks.find((c) => c.id === view.check));
const platform = $derived(
  guidance?.platforms.find((p) => p.id === (chosen?.platform ?? view.platform)) ?? guidance?.platforms[0],
);
const mine = $derived(guidance?.checks.filter((c) => c.platform === platform?.id) ?? []);
const selected = $derived(
  chosen ?? mine.find((c) => c.id === platform?.defaultCheck) ?? mine.find((c) => c.lastPassed),
);
const at = (c: GuidanceCheck): View => ({ page: "home", platform: c.platform, check: c.id, params: [] });
function choose(platform: string) {
  const { check: _, ...rest } = view; // a new platform starts on its default check
  go({ ...rest, page: "home", platform });
}
// A check chosen in the grid below shows its set above: take keyboard focus (and the screen) there.
function pick(e: MouseEvent, c: GuidanceCheck) {
  follow(e, at(c));
  if (e.defaultPrevented) tick().then(() => document.getElementById("install-heading")?.focus());
}

// All checks as a grid: a row per platform and Python, a column per kind of check.
const columns = $derived([...new Set(guidance?.checks.map((c) => c.label) ?? [])]);
const rows = $derived.by(() => {
  const out = new Map<string, { label: string; cells: Map<string, GuidanceCheck> }>();
  for (const p of guidance?.platforms ?? []) {
    for (const c of guidance?.checks.filter((x) => x.platform === p.id) ?? []) {
      const key = `${p.id} ${c.python}`;
      const row = out.get(key) ?? { label: `${p.label} · Python ${c.python}`, cells: new Map() };
      row.cells.set(c.label, c);
      out.set(key, row);
    }
  }
  return [...out.values()].sort((a, b) => a.label.localeCompare(b.label, "en", { numeric: true }));
});

let grid = $state<HTMLDivElement>();
let overflowing = $state(false);
$effect(() => {
  if (!grid) return;
  const element = grid;
  const update = () => {
    overflowing = element.scrollWidth > element.clientWidth;
  };
  const observer = new ResizeObserver(update);
  observer.observe(element);
  if (element.firstElementChild) observer.observe(element.firstElementChild);
  update();
  return () => observer.disconnect();
});

const changes = $derived(latestChanges(index));
const moves = $derived(
  [changes.find((c) => c.way === "worse"), changes.find((c) => c.way === "better")].filter((c) => c !== undefined),
);
const comparison = $derived(guidance?.solverComparison);
const largest = $derived(Math.max(0, ...(comparison?.rows.map((r) => r.value) ?? [])));

// Links to the old compatibility view land on the grid.
$effect(() => {
  if (guidance && view.page === "compatibility") document.getElementById("all-checks")?.scrollIntoView();
});
</script>

<header class="home-intro">
  <div class="home-intro-main">
    <div class="home-kicker">
      <span class="home-kicker-title">Brightway Benchmarks</span>
      <span class="home-kicker-sep">·</span>
      <span class="home-kicker-tag">Evidence Workspace</span>
    </div>
    <div class="home-brand-lockup">
      <div class="home-emblem" aria-hidden="true">
        <LogoMark size={36} />
      </div>
      <h2>{guidance?.title ?? (index.project.name === "brightway-benchmarks" ? "Continuous benchmarks for the Brightway LCA stack" : index.project.name)}</h2>
    </div>
    <p>{guidance?.intro ?? index.project.description ?? "Explore benchmark measurements and release changes."}</p>
  </div>
  {#if guidance}
    <div class="home-intro-status">
      <span class="home-status-badge {statusTone(selected?.status ?? 'success')}">{statusLabel(selected?.status ?? "success")}</span>
      <p class="snapshot">Latest published checks<br/><a href={guidance.snapshot.run}>{dateLabel(guidance.snapshot.date)}</a></p>
    </div>
  {/if}
</header>

<div class="home-columns">
  <div class="setup-column">
    {#if guidance && platform}
      <div class="platform-tabs" role="group" aria-label="Choose a platform">{#each guidance.platforms as p (p.id)}<button type="button" aria-pressed={platform.id === p.id} onclick={() => choose(p.id)}>{p.label}</button>{/each}</div>
      {#if selected}
        <InstallSet {selected} checks={mine} platform={platform.label} />
      {:else}
        <p class="no-saved">No passing set is published for {platform.label}. The checks below show what was tried.</p>
      {/if}

      <section class="all-checks" id="all-checks" aria-labelledby="all-checks-heading">
        <h2 id="all-checks-heading"><span class="desktop-checks">All checks</span><span class="phone-checks">{platform.label} checks</span></h2>
        <p class="check-scroll-hint desktop-checks" hidden={!overflowing}>Scroll to see all check types.</p>
        <ul class="platform-checks phone-checks" aria-label="{platform.label} checks">
          {#each mine as c (c.id)}
            <li><a href={writeView(at(c))} onclick={(e) => pick(e, c)} aria-current={c.id === selected?.id ? "true" : undefined}><span><span class="sr">{platform.label} · </span>{c.label}{" "}<small>Python {c.python}</small></span>{" "}<strong class={statusTone(c.status)}>{statusLabel(c.status)}</strong></a></li>
          {/each}
        </ul>
        <!-- svelte-ignore a11y_no_noninteractive_tabindex: the table scrolls inside a keyboard-focusable region -->
        <div class="scroll desktop-checks" role="region" aria-label="Check grid" tabindex="0" bind:this={grid}>
          <table class="check-grid">
            <caption>Select a check to install its set above.</caption>
            <thead><tr><th scope="col">Platform</th>{#each columns as col (col)}<th scope="col">{col}</th>{/each}</tr></thead>
            <tbody>
              {#each rows as row (row.label)}
                <tr>
                  <th scope="row">{row.label}</th>
                  {#each columns as col (col)}
                    {@const c = row.cells.get(col)}
                    <td>
                      {#if c}<a href={writeView(at(c))} onclick={(e) => pick(e, c)} aria-current={c.id === selected?.id ? "true" : undefined} class={statusTone(c.status)} aria-label="{row.label}, {col}: {statusLabel(c.status)}">{statusLabel(c.status)}</a>
                      {:else}<span class="quiet" aria-label="not checked">–</span>{/if}
                    </td>
                  {/each}
                </tr>
              {/each}
            </tbody>
          </table>
        </div>
        <dl class="check-kinds">
          {#each ["smoke", "suites", "diagnostic"] as const as kind (kind)}
            <dt>{checkKind(kind)}</dt>
            <dd>{{ smoke: "Install the latest releases and run each benchmark case once on a small database.", suites: "Run each package's own tests against that install.", diagnostic: "The same calculations on dependency floors, pre-releases or conda-forge, to see what breaks first." }[kind]}</dd>
          {/each}
        </dl>
      </section>
    {:else if !ready}<p class="empty" aria-live="polite">Loading tested setups…</p>
    {:else}<section><h2>Explore the available evidence</h2><p class="coverage-text">Setup guidance is unavailable. Benchmark histories and release changes remain available.</p><a href={writeView({ page: "explorer", params: [] })} onclick={(e) => follow(e, { page: "explorer", params: [] })}>Open the benchmarks</a></section>{/if}
  </div>

  <div class="evidence-column">
    {#if comparison}
      <section class="solver-evidence" aria-labelledby="solver-heading"><h2 id="solver-heading">{comparison.title}</h2><p>{comparison.context}</p>
        {#if platform && comparison.platform && comparison.platform !== platform.id}<p class="measurement-note">No {platform.label} machine was timed, so these values may not hold there.</p>{/if}
        <table><caption>Recorded measurements; follow a solver to inspect its benchmark.</caption><thead><tr><th scope="col">Solver</th><th scope="col" class="solver-bar-column">Relative time</th><th scope="col" class="num">Measured value</th></tr></thead><tbody>{#each comparison.rows as row (row.label)}<tr><th scope="row"><a href={row.href}>{row.label}</a></th><td class="solver-bar-column"><div class="solver-track" aria-hidden="true"><span style:width={`${largest > 0 ? (row.value / largest) * 100 : 0}%`}></span></div></td><td class="num">{format(row.value, row.unit)}</td></tr>{/each}</tbody></table>
        {#if comparison.note}<p class="measurement-note">{comparison.note}</p>{/if}
      </section>
    {:else if guidance}
      <p class="measurement-note solver-pending">The solver comparison is being measured again. <a href={writeView({ page: "explorer", params: [] })} onclick={(e) => follow(e, { page: "explorer", params: [] })}>Compare solvers in the benchmarks</a>.</p>
    {/if}

    <Findings {index} {follow} />

    <section class="release-brief" aria-labelledby="release-brief-heading">
      <h2 id="release-brief-heading">What changed?</h2><p>Changes beyond measured noise in each package's latest release.</p>
      {#each moves as row (row.change.case + row.change.machine + row.way)}
        {@const next = { bench: row.bench.id, params: row.params, measure: row.change.measure, machine: row.change.machine }}
        <article class="brief-change"><div><h3><a href={writeView(next)} onclick={(e) => follow(e, next)}>{benchmarkLabel(row.bench.name)}</a></h3><strong class={row.way}>{percent(row.change.ratio)} {row.way}</strong></div><p>{row.env} · beyond {noiseText(row.change)} noise</p><p class="brief-context">{row.group.name} · {row.from} → {row.to}{#if index.machines.length > 1} · {index.machines.find((m) => m.id === row.change.machine)?.name}{/if}</p></article>
      {/each}
      {#if moves.length === 0}<p class="coverage-text">No release changes beyond measured noise were published.</p>{/if}
      <a class="section-link" href={writeView({ page: "explorer", params: [] })} onclick={(e) => follow(e, { page: "explorer", params: [] })}>Open all release changes</a>
    </section>
  </div>
</div>
