<script lang="ts">
import type { BenchmarkIndex } from "../lib/contract";
import { type View, writeView } from "../lib/history";

// `wide`: two columns, for the Benchmarks overview; Setup's narrower column lists them.
// `shownElsewhere`: views the page already shows, such as Setup's solver comparison; a finding about one is left out.
let {
  index,
  follow,
  wide = false,
  shownElsewhere = [],
  all,
}: {
  index: BenchmarkIndex;
  follow: (event: MouseEvent, view: View) => void;
  wide?: boolean;
  shownElsewhere?: View[];
  /** The findings page: these cards are its preview. */
  all?: string;
} = $props();
const same = (f: { benchmark: string; params: string[] }, v: View) =>
  v.bench === f.benchmark && v.params.join("\n") === f.params.join("\n");
const shown = $derived(
  (index.findings ?? []).filter(
    (f) => index.benchmarks.some((b) => b.id === f.benchmark) && !shownElsewhere.some((v) => same(f, v)),
  ),
);
</script>

{#if shown.length}
  <section class="findings" class:wide aria-labelledby="findings-heading">
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
