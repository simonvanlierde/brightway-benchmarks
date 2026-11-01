<script lang="ts">
import type { BenchmarkIndex, Guidance } from "../lib/contract";
import { checkKind, dateLabel, statusLabel, statusTone } from "../lib/guidance";
import { benchmarkLabel, format, latestChanges, noiseText, percent, type View, writeView } from "../lib/history";
import CheckDetail from "./CheckDetail.svelte";

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
const platform = $derived(guidance?.platforms.find((p) => p.id === view.platform) ?? guidance?.platforms[0]);
const check = $derived(
  guidance?.checks.find((c) => c.id === platform?.defaultCheck && c.platform === platform?.id && c.lastPassed),
);
const related = $derived(guidance?.checks.filter((c) => c.platform === platform?.id) ?? []);
const changes = $derived(latestChanges(index));
const moves = $derived(
  [changes.find((c) => c.way === "worse"), changes.find((c) => c.way === "better")].filter((c) => c !== undefined),
);
const additional = $derived(related.filter((c) => c.kind === "suites" || c.status !== "success"));
const comparison = $derived(guidance?.solverComparison);
const largest = $derived(Math.max(0, ...(comparison?.rows.map((r) => r.value) ?? [])));
</script>

<header class="home-intro">
  <div><h2>{guidance?.title ?? index.project.name}</h2><p>{guidance?.intro ?? index.project.description ?? "Explore benchmark measurements and release changes."}</p></div>
  {#if guidance}<p class="snapshot">Latest published checks<br/><a href={guidance.snapshot.run}>{dateLabel(guidance.snapshot.date)}</a></p>{/if}
</header>

<div class="home-columns">
  <div class="home-evidence">
    {#if guidance && platform}
      <section class="setup-panel" aria-labelledby="setup-heading">
        <div class="setup-heading"><h2 id="setup-heading">Your starting point</h2><span>{platform.label}{#if check}{` · Python ${check.python}`}{/if}</span></div>
        <div class="platform-tabs" role="group" aria-label="Choose a platform">{#each guidance.platforms as p(p.id)}<button type="button" aria-pressed={platform.id===p.id} onclick={()=>go({...view,page:"home",platform:p.id})}>{p.label}</button>{/each}</div>
        {#if check}<CheckDetail {check}/>{:else}<p class="no-saved">No passing setup files are published for {platform.label}. Inspect compatibility for check coverage.</p>{/if}
        <div class="setup-coverage"><div><strong>Check coverage</strong><p>Smoke calculations and full upstream tests are separate checks.</p></div><a href={writeView({page:"compatibility",platform:platform.id,params:[]})} onclick={(e)=>follow(e,{page:"compatibility",platform:platform.id,params:[]})}>Inspect compatibility</a></div>
      </section>
    {:else if !ready}<p class="empty" aria-live="polite">Loading tested setups…</p>
    {:else}<section class="setup-panel"><h2>Explore the available evidence</h2><p class="coverage-text">Setup guidance is unavailable. Benchmark histories and release changes remain available.</p><a href={writeView({page:"explorer",params:[]})} onclick={(e)=>follow(e,{page:"explorer",params:[]})}>Open the benchmark explorer</a></section>{/if}

    {#if comparison}
      <section class="solver-evidence" aria-labelledby="solver-heading"><h2 id="solver-heading">{comparison.title}</h2><p>{comparison.context}</p>
        {#if platform && comparison.platform && comparison.platform !== platform.id}<p class="measurement-note">No {platform.label} machine was timed, so these values may not hold there.</p>{/if}
        <table><caption>Recorded measurements; follow a solver to inspect its benchmark.</caption><thead><tr><th scope="col">Solver</th><th scope="col" class="solver-bar-column">Relative time</th><th scope="col" class="num">Measured value</th></tr></thead><tbody>{#each comparison.rows as row(row.label)}<tr><th scope="row"><a href={row.href}>{row.label}</a></th><td class="solver-bar-column"><div class="solver-track" aria-hidden="true"><span style:width={`${largest > 0 ? row.value/largest*100 : 0}%`}></span></div></td><td class="num">{format(row.value,row.unit)}</td></tr>{/each}</tbody></table>
        {#if comparison.note}<p class="measurement-note">{comparison.note}</p>{/if}
      </section>
    {/if}
  </div>
  <section class="release-brief" aria-labelledby="release-brief-heading">
    <h2 id="release-brief-heading">What changed?</h2><p>Changes beyond measured noise in each package's latest release.</p>
    {#each moves as row(row.change.case+row.change.machine+row.way)}
      {@const next={bench:row.bench.id,params:row.params,measure:row.change.measure,machine:row.change.machine}}
      <article class="brief-change"><div><h3><a href={writeView(next)} onclick={(e)=>follow(e,next)}>{benchmarkLabel(row.bench.name)}</a></h3><strong class={row.way}>{percent(row.change.ratio)} {row.way}</strong></div><p>{row.env} · beyond {noiseText(row.change)} noise</p><p class="brief-context">{row.group.name} · {row.from} → {row.to}{#if index.machines.length>1} · {index.machines.find(m=>m.id===row.change.machine)?.name}{/if}</p></article>
    {/each}
    {#if moves.length===0}<p class="coverage-text">No release changes beyond measured noise were published.</p>{/if}
    <a class="section-link" href={writeView({page:"changes",params:[]})} onclick={(e)=>follow(e,{page:"changes",params:[]})}>Open all release changes</a>
    {#if related.length}<section class="current-coverage"><h3>Current check coverage</h3><ul>{#each additional.slice(0,4) as cell(cell.id)}<li><a href={writeView({page:"compatibility",platform:cell.platform,check:cell.id,params:[]})} onclick={(e)=>follow(e,{page:"compatibility",platform:cell.platform,check:cell.id,params:[]})}>{cell.label} · Python {cell.python}</a><span class={statusTone(cell.status)}>{checkKind(cell.kind)} · {statusLabel(cell.status)}</span></li>{/each}</ul>{#if additional.length===0}<p>No full upstream test-suite result is published for this platform.</p>{/if}<p>These checks cover installation and calculations; they are separate from timing regressions.</p></section>{/if}

  </section>
</div>
