<script lang="ts">
import { checkKind, dateLabel, type GuidanceCheck, statusLabel } from "../lib/guidance";

let { check }: { check: GuidanceCheck } = $props();
const saved = $derived(check.lastPassed);
const primary = $derived(saved?.files[0]);
</script>

<div class="check-detail">
  <p class="check-outcome" class:better={check.status === "success"} class:worse={check.status === "failure" || check.status === "timed_out"}>
    {checkKind(check.kind)} · {statusLabel(check.status)}
  </p>
  <p class="coverage-text">{check.coverage}</p>
  {#if check.caveats.length}<ul class="caveats">{#each check.caveats as caveat(caveat)}<li>{caveat}</li>{/each}</ul>{/if}
  <a class="check-run" href={check.run}>Inspect this check</a>
  {#if saved}
    <div class="saved-set">
      <div class="saved-header"><h3>Install the last passing set</h3><p>{dateLabel(saved.date)} · <a href={saved.run}>Passing run</a></p></div>
      {#if check.status !== "success"}<p class="saved-warning">The current check did not pass. These files belong to the earlier passing run above.</p>{/if}
      <div class="setup-content">
        <div class="install-panel">
          {#if primary}<a class="primary-action" href={primary.url}>Download {primary.label}</a>{/if}
          <div class="environment-files">{#each saved.files.filter(f=>f!==primary) as file(file.url)}<a href={file.url}>{file.label}</a>{/each}</div>
          {#if saved.install}<div class="install-command"><div><strong>Install this tested set</strong></div><pre><code>{saved.install}</code></pre></div>{/if}
        </div>
        <div class="package-pins"><h3>Verified package versions</h3><table aria-label="Tested package versions"><tbody>{#each saved.packages as pkg(pkg.name)}<tr><th scope="row">{pkg.name}</th><td>{pkg.version}</td></tr>{/each}</tbody></table>

        </div>
      </div>
    </div>
  {:else}
    <p class="no-saved">No passing environment files have been published for this check. Inspect its run for the available evidence.</p>
  {/if}
</div>
