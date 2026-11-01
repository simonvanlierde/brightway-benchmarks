<script lang="ts">
import { tick } from "svelte";
import type { Guidance } from "../lib/contract";
import { checkKind, dateLabel, statusLabel } from "../lib/guidance";
import { type View, writeView } from "../lib/history";
import CheckDetail from "./CheckDetail.svelte";

let {
  guidance,
  ready,
  view,
  go,
  follow,
}: {
  guidance: Guidance | undefined;
  ready: boolean;
  view: View;
  go: (view: View) => void;
  follow: (event: MouseEvent, view: View) => void;
} = $props();
const checks = $derived(
  guidance?.checks.filter(
    (c) => (!view.platform || c.platform === view.platform) && (!view.python || c.python === view.python),
  ) ?? [],
);
const versions = $derived([...new Set(guidance?.checks.map((c) => c.python) ?? [])]);
const selected = $derived(
  checks.find((c) => c.id === view.check) ??
    guidance?.platforms.map((p) => checks.find((c) => c.id === p.defaultCheck)).find(Boolean) ??
    checks[0],
);
const platformName = (id: string) => guidance?.platforms.find((p) => p.id === id)?.label ?? id;
async function inspect(event: MouseEvent, next: View) {
  const normal = !event.metaKey && !event.ctrlKey && !event.shiftKey && event.button === 0;
  follow(event, next);
  if (!normal || !matchMedia("(max-width:75rem)").matches) return;
  await tick();
  const detail = document.getElementById("selected-check");
  detail?.focus({ preventScroll: true });
  detail?.scrollIntoView({ block: "start" });
}
</script>

<header class="home-intro"><div><h2>Compatibility</h2><p>Compare the environments that were checked. Open a row for its coverage, results and last passing environment files.</p></div>{#if guidance}<p class="snapshot">Latest published checks<br/><a href={guidance.snapshot.run}>{dateLabel(guidance.snapshot.date)}</a></p>{/if}</header>
{#if !guidance}<p class="empty">{ready ? "No compatibility guidance is published." : "Loading compatibility checks…"}</p>
{:else}<div class="compat-workspace"><section class="compat-table-area" aria-label="Compatibility checks">
  <div class="compat-filters"><div><label for="compat-platform">Platform</label><select id="compat-platform" value={view.platform ?? ""} onchange={(e)=>go({...view,page:"compatibility",platform:e.currentTarget.value,check:""})}><option value="">All platforms</option>{#each guidance.platforms as platform(platform.id)}<option value={platform.id}>{platform.label}</option>{/each}</select></div><div><label for="compat-python">Python</label><select id="compat-python" value={view.python ?? ""} onchange={(e)=>go({...view,page:"compatibility",python:e.currentTarget.value,check:""})}><option value="">All tested versions</option>{#each versions as python(python)}<option>{python}</option>{/each}</select></div><p>{checks.length} checks shown</p></div>
  {#if checks.length===0}<p class="empty">No checks match this platform and Python version. Change either filter to see the available evidence.</p>{:else}
  <!-- svelte-ignore a11y_no_noninteractive_tabindex: the table scrolls inside a keyboard-focusable region -->
  <div class="scroll compat-table-scroll" role="region" aria-label="Tested environments" tabindex="0"><table class="compat-table"><caption>Select a check to inspect its exact coverage and saved files.</caption><thead><tr><th scope="col">Platform / Python</th><th scope="col">Environment</th><th scope="col">Check</th><th scope="col">Result</th></tr></thead><tbody>{#each checks as check(check.id)}{@const next={...view,page:"compatibility",check:check.id}}<tr class:selected={selected?.id===check.id}><th scope="row"><a href={writeView(next)} aria-current={selected?.id===check.id ? "true" : undefined} onclick={(e)=>inspect(e,next)} aria-label={`Inspect ${platformName(check.platform)} Python ${check.python} ${check.label}`}>{platformName(check.platform)}</a><span class="cell-subline">Python {check.python}</span></th><td>{check.label}</td><td>{checkKind(check.kind)}</td><td class:better={check.status==="success"} class:worse={check.status==="failure" || check.status==="timed_out"}>{statusLabel(check.status)}</td></tr>{/each}</tbody></table></div>{/if}
  <p class="compat-note">A smoke pass and a full upstream test-suite pass are different claims. Each check's detail names its coverage and limitations.</p>
  <a href={writeView({page:"changes",params:[]})} onclick={(e)=>follow(e,{page:"changes",params:[]})}>Inspect release-to-release performance changes</a>
</section>{#if selected}<aside class="compat-detail" id="selected-check" tabindex="-1" aria-label="Selected check"><header><h2>{platformName(selected.platform)} · Python {selected.python}</h2><p>{selected.label}</p></header><CheckDetail check={selected}/></aside>{/if}</div>{/if}
