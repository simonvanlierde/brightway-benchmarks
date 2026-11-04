<script lang="ts">
import { tick } from "svelte";
import type { BenchmarkIndex, Guidance } from "../lib/contract";
import { dateLabel, type GuidanceCheck, statusLabel, statusTone } from "../lib/guidance";
import {
  benchmarkLabel,
  byBenchmark,
  format,
  latestChanges,
  noiseText,
  percentRange,
  readView,
  type View,
  writeView,
} from "../lib/history";
import Findings from "./Findings.svelte";
import InstallSet from "./InstallSet.svelte";

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
  // The select moves in or out of InstallSet when the platform has no passing set: keep its focus.
  const focused = document.activeElement?.id === "setup-platform";
  go({ ...rest, page: "home", platform });
  if (focused) tick().then(() => document.getElementById("setup-platform")?.focus());
}
// A check chosen in the grid below shows its set above: take keyboard focus (and the screen) there.
function pick(e: MouseEvent, c: GuidanceCheck) {
  follow(e, at(c));
  if (e.defaultPrevented) tick().then(() => document.getElementById("install-heading")?.focus());
}

// All checks as a grid: a row per platform and Python, a column per kind of check.
const columns = $derived([...new Map(guidance?.checks.map((c) => [c.label, c]) ?? []).values()]);
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
// The largest regression, one case, and the benchmark with the largest gain, all its cases: as Benchmarks lists them.
const moves = $derived(
  [
    changes.filter((c) => c.way === "worse").slice(0, 1),
    byBenchmark(changes.filter((c) => c.way === "better"))[0]?.rows ?? [],
  ].filter((rows) => rows.length > 0),
);
const comparison = $derived(guidance?.solverComparison);
// The findings below leave out the comparison above: one fact, one set of numbers on the page.
const compared = $derived(comparison?.rows.map((r) => readView(new URL(r.href, "https://x/").search)) ?? []);
const largest = $derived(Math.max(0, ...(comparison?.rows.map((r) => r.value) ?? [])));

// Links to the old compatibility view land on the grid.
$effect(() => {
  if (guidance && view.page === "compatibility") document.getElementById("all-checks")?.scrollIntoView();
});
</script>

<header class="home-intro">
  <h2>{guidance?.title ?? index.project.name}</h2>
  <p><a href="https://docs.brightway.dev/en/latest/">Brightway</a> is the open-source Python framework for life cycle assessment (LCA). What you install alongside it decides whether it runs, and how fast: the same score can take ten times longer with a different solver. Every night this site installs Brightway on Linux, macOS and Windows and runs its tests, and it times every release on one fixed machine. {guidance?.intro ?? index.project.description ?? ""}</p>
</header>

<div class="home-columns">
  <div class="setup-column">
    {#if guidance && platform}
      {#snippet platformChoice()}
        <label class="control-label" for="setup-platform">Operating system</label>
        <select id="setup-platform" value={platform.id} onchange={(e) => choose(e.currentTarget.value)}>
          {#each guidance.platforms as p (p.id)}<option value={p.id}>{p.label}</option>{/each}
        </select>
      {/snippet}
      {#if selected}
        <InstallSet {selected} checks={mine} platform={platform.label} {platformChoice} explicitCheck={!!chosen} onSelectCheck={(c) => go({ page: "home", platform: c.platform, check: c.id, params: [] })} />
      {:else}
        {@render platformChoice()}
        <p class="no-saved">No passing set is published for {platform.label}. The checks below show what was tried.</p>
      {/if}

      <section class="all-checks" id="all-checks" aria-labelledby="all-checks-heading">
        <div class="checks-heading">
          <h2 id="all-checks-heading"><span class="desktop-checks">All checks</span><span class="phone-checks">{platform.label} checks</span></h2>
          <small class="checks-date"><a href={guidance.snapshot.run}>Checked {dateLabel(guidance.snapshot.date)}</a></small>
        </div>
        <div class="desktop-checks"><p class="check-help" id="check-instructions"><span>Select a check to view its install set above.</span><span hidden={!overflowing}>Scroll to see all check types.</span></p></div>
        <ul class="platform-checks phone-checks" aria-label="{platform.label} checks">
          {#each mine as c (c.id)}
            <li><a href={writeView(at(c))} onclick={(e) => pick(e, c)} aria-current={c.id === selected?.id ? "true" : undefined}><span><span class="sr">{platform.label} · </span><span class="check-name">{c.label}</span>{" "}<small>Python {c.python}</small></span>{" "}<strong class={statusTone(c.status)}>{statusLabel(c.status)}</strong></a></li>
          {/each}
        </ul>
        <!-- svelte-ignore a11y_no_noninteractive_tabindex: the table scrolls inside a keyboard-focusable region -->
        <div class="scroll desktop-checks" role="region" aria-label="Check grid" tabindex="0" bind:this={grid}>
          <table class="check-grid" aria-describedby="check-instructions">
            <caption class="sr">Compatibility checks by platform and Python version</caption>
            <thead><tr><th scope="col">Platform</th>{#each columns as col (col.label)}<th scope="col">{col.label}</th>{/each}</tr></thead>
            <tbody>
              {#each rows as row (row.label)}
                <tr>
                  <th scope="row">{row.label}</th>
                  {#each columns as col (col.label)}
                    {@const c = row.cells.get(col.label)}
                    <td>
                      {#if c}<a href={writeView(at(c))} onclick={(e) => pick(e, c)} aria-current={c.id === selected?.id ? "true" : undefined} class={statusTone(c.status)} aria-label="{row.label}, {col.label}: {statusLabel(c.status)}">{statusLabel(c.status)}</a>
                      {:else}<span class="quiet" aria-label="not checked">–</span>{/if}
                    </td>
                  {/each}
                </tr>
              {/each}
            </tbody>
          </table>
        </div>
        <dl class="check-kinds">
          {#each columns as col (col.label)}
            <dt>{col.label}</dt>
            <dd>{col.description ?? col.coverage}</dd>
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

    <Findings {index} {follow} shownElsewhere={compared} />

    <section class="release-brief" aria-labelledby="release-brief-heading">
      <h2 id="release-brief-heading">What changed in the latest releases</h2><p>Changes beyond measured noise in each package's latest release.</p>
      {#each moves as rows, i (i)}
        {@const row = rows[0]}
        {#if row}
        {@const next = { bench: row.bench.id, params: row.params, measure: row.change.measure, machine: row.change.machine }}
        <article class="brief-change"><div><h3><a href={writeView(next)} onclick={(e) => follow(e, next)}>{benchmarkLabel(row.bench.name)}</a></h3><strong class={row.way}>{percentRange(rows)} {row.way}</strong></div><p>{#if rows.length > 1}{rows.length} cases, each beyond its noise{:else}{row.env} · beyond {noiseText(row.change)} noise{/if}</p><p class="brief-context">{row.group.name} · {row.from} → {row.to}{#if index.machines.length > 1} · {index.machines.find((m) => m.id === row.change.machine)?.name}{/if}</p></article>
        {/if}
      {/each}
      {#if moves.length === 0}<p class="coverage-text">No release changes beyond measured noise were published.</p>{/if}
      <a class="section-link" href={writeView({ page: "explorer", params: [] })} onclick={(e) => follow(e, { page: "explorer", params: [] })}>Open all release changes</a>
    </section>
  </div>
</div>
