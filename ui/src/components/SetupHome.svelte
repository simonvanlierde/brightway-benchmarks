<script lang="ts">
import { tick } from "svelte";
import type { BenchmarkIndex, Guidance } from "../lib/contract";
import { dateLabel, type GuidanceCheck, statusLabel, statusTone } from "../lib/guidance";
import { benchLabel, byBenchmark, format, latestChanges, percentRange, type View, writeView } from "../lib/history";
import { supportLead, supportTable } from "../lib/pythonSupport";
import { scrollable } from "../lib/scrollable";
import InstallSet from "./InstallSet.svelte";

let {
  guidance,
  ready,
  index,
  view,
  go,
  follow,
  name,
  findings,
}: {
  guidance: Guidance | undefined;
  ready: boolean;
  index: BenchmarkIndex;
  view: View;
  go: (view: View) => void;
  follow: (event: MouseEvent, view: View) => void;
  /** The site's display name, as the masthead shows it. */
  name: string;
  /** The findings page, for the nudge beside the install set. */
  findings?: string;
} = $props();
const chosen = $derived(guidance?.checks.find((c) => c.id === view.check));
// With no platform in the address, start on the visitor's own system; the select still changes it.
const ua =
  (navigator as Navigator & { userAgentData?: { platform: string } }).userAgentData?.platform || navigator.platform;
const detected = /win/i.test(ua) ? "windows" : /mac/i.test(ua) ? "macos" : /linux|x11/i.test(ua) ? "linux" : undefined;
const platform = $derived(
  guidance?.platforms.find((p) => p.id === (chosen?.platform ?? view.platform ?? detected)) ?? guidance?.platforms[0],
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

let overflowing = $state(false);

const changes = $derived(latestChanges(index));
// The largest regression, one case, and the benchmark with the largest gain, all its cases: as Benchmarks lists them.
const moves = $derived(
  [
    changes.filter((c) => c.way === "worse").slice(0, 1),
    byBenchmark(changes.filter((c) => c.way === "better"))[0]?.rows ?? [],
  ].filter((rows) => rows.length > 0),
);
const comparison = $derived(guidance?.solverComparison);
// The solver nudge quotes the comparison's own figures, so Setup and Benchmarks never disagree.
const slowest = $derived(comparison?.rows.find((r) => r.label === "SuperLU"));
const fastest = $derived(comparison?.rows.find((r) => r.label.startsWith("UMFPACK")));
// The daily Python probe, as one line under the Python select; Benchmarks has its full table.
const pythonSupport = $derived(guidance?.pythonSupport && supportTable(guidance.pythonSupport, false));
const pythonNote = $derived(
  pythonSupport && {
    text: supportLead(pythonSupport, (id) => guidance?.platforms.find((p) => p.id === id)?.label ?? id),
    href: `${writeView({ page: "explorer", params: [] })}#python-support`,
  },
);

// Links to the old compatibility view land on the grid.
$effect(() => {
  if (guidance && view.page === "compatibility") document.getElementById("all-checks")?.scrollIntoView();
});
</script>

<div class="home-columns">
  <div class="setup-column">
    <header class="home-intro">
      <h2>{guidance?.title ?? name}</h2>
      <p>Every night we check that the latest <a href="https://docs.brightway.dev/en/latest/">Brightway</a> releases install and work together on Linux, macOS and Windows. {guidance?.intro ?? index.project.description ?? ""}</p>
    </header>
    {#if guidance && platform}
      {#snippet platformChoice()}
        <label class="control-label" for="setup-platform">Operating system</label>
        <select id="setup-platform" value={platform.id} onchange={(e) => choose(e.currentTarget.value)}>
          {#each guidance.platforms as p (p.id)}<option value={p.id}>{p.label}</option>{/each}
        </select>
      {/snippet}
      {#if selected}
        <InstallSet {selected} checks={mine} platform={platform.label} {platformChoice} {pythonNote} explicitCheck={!!chosen} onSelectCheck={(c) => go({ page: "home", platform: c.platform, check: c.id, params: [] })} />
      {:else}
        {@render platformChoice()}
        <p class="no-saved">No passing set is published for {platform.label}. The checks show what was tried.</p>
      {/if}

    {:else if !ready}<p class="empty" aria-live="polite">Loading tested setups…</p>
    {:else}<section><h2>Explore the available evidence</h2><p class="coverage-text">Setup guidance is unavailable. Benchmark histories and release changes remain available.</p><a href={writeView({ page: "explorer", params: [] })} onclick={(e) => follow(e, { page: "explorer", params: [] })}>Open the benchmarks</a></section>{/if}
  </div>

  <div class="evidence-column">
    {#if guidance && platform}
      <section class="all-checks" id="all-checks" aria-labelledby="all-checks-heading">
        <div class="checks-heading">
          <h2 id="all-checks-heading">Checks</h2>
          <small class="checks-date">Checked {dateLabel(guidance.snapshot.date)} · <a href={guidance.snapshot.run}>open the run</a></small>
        </div>
        <div class="desktop-checks"><p class="check-help" id="check-instructions"><span>Select a check to show its install set.</span><span hidden={!overflowing}>Scroll to see all check types.</span></p></div>
        <div class="phone-checks"><p class="check-showing">Showing {platform.label}. Change the operating system above for the others.</p></div>
        <ul class="platform-checks phone-checks" aria-label="{platform.label} checks">
          {#each mine as c (c.id)}
            <li><a href={writeView(at(c))} onclick={(e) => pick(e, c)} aria-current={c.id === selected?.id ? "true" : undefined}><span><span class="sr">{platform.label} · </span><span class="check-name">{c.label}</span>{" "}<small>Python {c.python}</small></span>{" "}<strong class={statusTone(c.status)}>{statusLabel(c.status)}</strong></a></li>
          {/each}
        </ul>
        <div class="scroll desktop-checks" role="region" aria-label="Check grid" use:scrollable={(over) => (overflowing = over)}>
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
                      {:else}<span class="quiet" aria-hidden="true">–</span><span class="sr">not checked</span>{/if}
                    </td>
                  {/each}
                </tr>
              {/each}
            </tbody>
          </table>
        </div>
        <details class="check-kinds-details">
          <summary>What each check covers</summary>
          <dl class="check-kinds">
            {#each columns as col (col.label)}
              <dt>{col.label}</dt>
              <dd>{col.description ?? col.coverage}</dd>
            {/each}
          </dl>
        </details>
      </section>
    {/if}
  <aside class="nudges" aria-labelledby="nudges-heading">
    <h2 id="nudges-heading">From the benchmarks</h2>
    <ul>
      {#if slowest && fastest}
        <li><a href={writeView({ page: "explorer", params: [] })} onclick={(e) => follow(e, { page: "explorer", params: [] })}>Which solver to install</a><span>One score: {format(slowest.value, slowest.unit)} with SciPy's SuperLU, {format(fastest.value, fastest.unit)} with UMFPACK from conda-forge.</span></li>
      {/if}
      {#each moves as rows, i (i)}
        {@const row = rows[0]}
        {#if row}
          {@const next = { bench: row.bench.id, params: row.params, measure: row.change.measure, machine: row.change.machine }}
          <li><a href={writeView(next)} onclick={(e) => follow(e, next)}>{benchLabel(index, row.bench)}</a><span><strong class={row.way}>{percentRange(rows)} {row.way}</strong> in {row.group.label ?? row.group.name} {row.to}</span></li>
        {/if}
      {/each}
      {#if findings}<li><a href={findings}>What the benchmarks found</a><span>Release regressions, fixes and the solver story, each with its write-up.</span></li>{/if}
    </ul>
  </aside>
  </div>
</div>
