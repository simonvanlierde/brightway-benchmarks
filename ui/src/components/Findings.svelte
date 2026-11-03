<script lang="ts">
import type { BenchmarkIndex } from "../lib/contract";
import { type View, writeView } from "../lib/history";

// `wide`: two columns, for the Benchmarks overview; Setup's narrower column lists them.
let {
  index,
  follow,
  wide = false,
}: { index: BenchmarkIndex; follow: (event: MouseEvent, view: View) => void; wide?: boolean } = $props();
const shown = $derived((index.findings ?? []).filter((f) => index.benchmarks.some((b) => b.id === f.benchmark)));
</script>

{#if shown.length}
  <section class="findings" class:wide aria-labelledby="findings-heading">
    <h2 id="findings-heading">What the benchmarks show</h2>
    <ul>
      {#each shown as f (f.title)}
        {@const next = { bench: f.benchmark, params: f.params, page: "explorer" }}
        <li>
          <h3><a href={writeView(next)} onclick={(e) => follow(e, next)}>{f.title}</a></h3>
          <p>{f.text}{#if f.url}{" "}<a class="quiet-link" href={f.url}>Full account</a>{/if}{#if f.profile}{" "}<a class="quiet-link" href={f.profile}>Profile</a>{/if}</p>
        </li>
      {/each}
    </ul>
  </section>
{/if}
