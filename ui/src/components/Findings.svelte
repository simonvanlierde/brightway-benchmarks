<script lang="ts">
import type { BenchmarkIndex } from "../lib/contract";
import { type View, writeView } from "../lib/history";

let {
  index,
  follow,
  all,
}: {
  index: BenchmarkIndex;
  follow: (event: MouseEvent, view: View) => void;
  /** The findings page: these cards are its preview. */
  all?: string | undefined;
} = $props();
const shown = $derived((index.findings ?? []).filter((f) => index.benchmarks.some((b) => b.id === f.benchmark)));
</script>

{#if shown.length}
  <section class="findings wide" aria-labelledby="findings-heading">
    <h2 id="findings-heading">What the benchmarks show</h2>
    <ul>
      {#each shown as f (f.title)}
        {@const next = { bench: f.benchmark, params: f.params, page: "explorer" }}
        <li>
          <h3><a href={writeView(next)} onclick={(e) => follow(e, next)}>{f.title}</a></h3>
          <p>{f.text}{#if f.url}{" "}<a class="quiet-link" href={f.url}>Write-up<span class="sr"> on {f.title}</span></a>{/if}{#if f.profile}{" "}<a class="quiet-link" href={f.profile}>Profile<span class="sr"> for {f.title}</span></a>{/if}</p>
        </li>
      {/each}
    </ul>
    {#if all}<a class="section-link" href={all}>All findings</a>{/if}
  </section>
{/if}
