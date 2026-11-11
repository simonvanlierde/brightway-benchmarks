<script lang="ts">
import type { Guidance } from "../lib/contract";
import { dateLabel } from "../lib/guidance";
import { codeParts, listed, supportLead, supportTable, supportWord } from "../lib/pythonSupport";
import { scrollable } from "../lib/scrollable";

// `eol`: the Pythons past end of life, for maintainers; otherwise the supported ones, for users.
let { guidance, eol = false }: { guidance: Guidance; eol?: boolean } = $props();
const support = $derived(guidance.pythonSupport);
const table = $derived(support && supportTable(support, eol));
const label = (id: string) => guidance.platforms.find((p) => p.id === id)?.label ?? id;
const several = $derived(new Set(table?.rows.map((r) => r.platform)).size > 1);
const heading = $derived(eol ? "End-of-life Pythons" : "Python versions");
const id = $derived(eol ? "eol-python" : "python-support");
const tone = { pass: "better", fail: "worse", undeclared: "undeclared" } as const;
</script>

{#if table}
  <section class="python-support" aria-labelledby="{id}-heading">
    <div class="checks-heading">
      <h2 id="{id}-heading">{heading}</h2>
      {#if table.checked}<small class="support-date">Checked {dateLabel(table.checked)}{#if table.run}{" · "}<a href={table.run}>open the run</a>{/if}</small>{/if}
    </div>
    {#if eol}
      <p class="coverage-text">Some releases of these packages still declare Python {listed(table.pythons)}, which are past end of life. Checked weekly on {listed([...new Set(table.rows.map((r) => label(r.platform)))])}.</p>
    {:else}
      {@const lead = supportLead(table, label)}
      {#if lead}<p class="support-lead">{lead}</p>{/if}
      <p class="coverage-text">Does your Python version work? A daily check installs each package on each Python, imports it and runs a small LCA. Failures stay on the table with the error.</p>
    {/if}
    <div class="scroll" role="region" aria-label="{heading} grid" use:scrollable>
      <table class="check-grid support-grid">
        <caption class="sr">Result by package{several ? ", system" : ""} and Python version</caption>
        <thead>
          <tr>
            <th scope="col">Package{several ? " and system" : ""}</th>
            {#each table.pythons as py (py)}<th scope="col"><span class="sr">{"Python "}</span>{py}</th>{/each}
          </tr>
        </thead>
        <tbody>
          {#each table.rows as row (`${row.package} ${row.platform}`)}
            <tr>
              <th scope="row"><code>{row.package}</code>{#if several}{" "}<span class="quiet">{label(row.platform)}</span>{/if}</th>
              {#each table.pythons as py (py)}
                {@const r = row.cells.get(py)}
                <td>
                  {#if r?.status === "fail"}<a href={r.run} class={tone[r.status]} aria-label="{row.package}{several ? `, ${label(row.platform)}` : ''}, Python {py}: {supportWord(r.status)}">{supportWord(r.status)}</a>
                  {:else if r}<span class={tone[r.status]}>{supportWord(r.status)}</span>
                  {:else}<span class="quiet" aria-hidden="true">–</span><span class="sr">not checked</span>{/if}
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
          <dt>{`Python ${listed(f.pythons)}${several ? ` on ${listed(f.platforms.map(label))}` : ""}: ${listed(f.packages)}`}</dt>
          <dd>{#each codeParts(f.reason) as part, i (i)}{#if part.code}<code>{part.text}</code>{:else}{part.text}{/if}{/each}</dd>
        {/each}
      </dl>
    {/if}
  </section>
{/if}
