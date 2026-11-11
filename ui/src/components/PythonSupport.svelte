<script lang="ts">
import type { Guidance } from "../lib/contract";
import { dateLabel } from "../lib/guidance";
import { listed, supportTable, supportWord } from "../lib/pythonSupport";

// `eol`: the Pythons past end of life, for maintainers; otherwise the supported ones, for users.
let { guidance, eol = false }: { guidance: Guidance; eol?: boolean } = $props();
const support = $derived(guidance.pythonSupport);
const table = $derived(support && supportTable(support, eol));
const label = (id: string) => guidance.platforms.find((p) => p.id === id)?.label ?? id;
const several = $derived(new Set(table?.rows.map((r) => r.platform)).size > 1);
const heading = $derived(eol ? "End-of-life Pythons" : "Python versions");
const id = $derived(eol ? "eol-python" : "python-support");
const tone = { pass: "better", fail: "worse", undeclared: "quiet" } as const;
</script>

{#if table}
  <section class="python-support" aria-labelledby="{id}-heading">
    <div class="checks-heading">
      <h2 id="{id}-heading">{heading}</h2>
      <small class="support-date">Oldest result {dateLabel(table.checked)}</small>
    </div>
    <p class="coverage-text">
      {#if eol}
        Some releases of these packages still declare Python {listed(table.pythons)}, which are past end of life. Checked weekly on {listed([...new Set(table.rows.map((r) => label(r.platform)))])}.
      {:else}
        Whether each package installs, imports and computes one score on a two-process system, from the daily run on each system. A failure stays on the table with its reason.
      {/if}
    </p>
    <!-- svelte-ignore a11y_no_noninteractive_tabindex: the table scrolls inside a keyboard-focusable region -->
    <div class="scroll" role="region" aria-label="{heading} grid" tabindex="0">
      <table class="check-grid support-grid">
        <caption class="sr">Result by package{several ? ", system" : ""} and Python version</caption>
        <thead>
          <tr>
            <th scope="col">Package{several ? " and system" : ""}</th>
            {#each table.pythons as py (py)}<th scope="col">Python {py}</th>{/each}
          </tr>
        </thead>
        <tbody>
          {#each table.rows as row (`${row.package} ${row.platform}`)}
            <tr>
              <th scope="row"><code>{row.package}</code>{#if several}{" "}<span class="quiet">{label(row.platform)}</span>{/if}</th>
              {#each table.pythons as py (py)}
                {@const r = row.cells.get(py)}
                <td>
                  {#if r}<a href={r.run} class={tone[r.status]} aria-label="{row.package}{several ? `, ${label(row.platform)}` : ''}, Python {py}: {supportWord(r.status)}">{supportWord(r.status)}</a>
                  {:else}<span class="quiet" aria-label="not checked">–</span>{/if}
                </td>
              {/each}
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
    {#if table.rows.some((r) => [...r.cells.values()].some((c) => c.status === "undeclared"))}
      <p class="coverage-text">Not declared: no release of the package supports that Python, so nothing was tried. This is not a failure.</p>
    {/if}
    {#if table.failures.length}
      <dl class="support-failures">
        {#each table.failures as f (f.reason)}
          <dt><code>{f.reason}</code></dt>
          <dd>{`Python ${listed(f.pythons)}${several ? ` on ${listed(f.platforms.map(label))}` : ""}: ${listed(f.packages)}`}</dd>
        {/each}
      </dl>
    {/if}
  </section>
{/if}
