<script lang="ts">
import { dateLabel, type GuidanceCheck } from "../lib/guidance";

type Manager = "uv" | "pip" | "conda" | "pixi";
const MANAGERS: Manager[] = ["uv", "pip", "conda", "pixi"];
const KEY = "bwbench.manager";

// `checks`: every check on the platform; a manager the selected check lacks comes from another of them.
let { selected, checks, platform }: { selected: GuidanceCheck; checks: GuidanceCheck[]; platform: string } = $props();

function stored(): Manager {
  try {
    const value = localStorage.getItem(KEY);
    return MANAGERS.includes(value as Manager) ? (value as Manager) : "uv";
  } catch {
    return "uv";
  }
}
let manager = $state<Manager>(stored());
function choose(next: Manager) {
  manager = next;
  copied = "";
  try {
    localStorage.setItem(KEY, next);
  } catch {
    // a private window: the choice lasts for this page only
  }
}

const has = (c: GuidanceCheck, m: Manager) => c.lastPassed?.installs.some((i) => i.manager === m) ?? false;
// The selected check first, then one on the same Python, then any other on the platform.
const source = $derived(
  has(selected, manager)
    ? selected
    : (checks.find((c) => c.python === selected.python && has(c, manager)) ?? checks.find((c) => has(c, manager))),
);
const saved = $derived(source?.lastPassed);
const install = $derived(saved?.installs.find((i) => i.manager === manager));

let copied = $state("");
async function copy(text: string, what: string) {
  try {
    await navigator.clipboard.writeText(text);
    copied = `Copied ${what}`;
  } catch {
    copied = "Copy failed; select the command instead";
  }
}
</script>

<section class="install-set" aria-labelledby="install-heading">
  <h2 id="install-heading" tabindex="-1">Install</h2>
  <div class="manager-tabs" role="group" aria-label="Package manager">
    {#each MANAGERS as m (m)}<button type="button" aria-pressed={manager === m} onclick={() => choose(m)}>{m}</button>{/each}
  </div>
  {#if source && saved && install}
    <div class="install-command">
      <pre><code>{install.command}</code></pre>
      <button type="button" class="copy" onclick={() => copy(install.command, "command")}>Copy</button>
    </div>
    <p class="install-meta">
      {#if saved.pinned && install.latest}
        {@const latest = install.latest}
        Pinned to {dateLabel(saved.pinned)} · <button type="button" class="text-button" onclick={() => copy(latest, "latest")}>Copy latest</button>
      {:else}
        Passed {dateLabel(saved.date)}
      {/if}
      <span role="status">{copied}</span>
    </p>
    {#if source !== selected}<p class="install-note">From the {source.label} check on Python {source.python}.</p>{/if}
    {#if source.status !== "success"}<p class="saved-warning">The latest {source.label} check did not pass; this is the set that passed on {dateLabel(saved.date)}.</p>{/if}
    <p class="environment-files">
      {#each saved.files as file (file.url)}<a href={file.url}>{file.label}</a>{/each}
      <a href={saved.run}>Passing run</a>
    </p>
    <details class="package-pins">
      <summary>{saved.packages.length} tested packages</summary>
      <table aria-label="Tested package versions"><tbody>{#each saved.packages as pkg (pkg.name)}<tr><th scope="row">{pkg.name}</th><td>{pkg.version}</td></tr>{/each}</tbody></table>
    </details>
  {:else}
    <p class="no-saved">No {manager} set has passed on {platform}. Choose another package manager, or a check below.</p>
  {/if}
</section>
