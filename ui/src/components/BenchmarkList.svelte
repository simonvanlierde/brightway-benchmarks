<script lang="ts">
import { type BenchmarkIndex, loadIndex } from "../lib/contract";

let { base }: { base: string } = $props();
let index = $state<BenchmarkIndex>();
let error = $state<string>();

$effect(() => {
  loadIndex(base).then(
    (data) => {
      index = data;
    },
    (reason: unknown) => {
      error = String(reason);
    },
  );
});
</script>

{#if error}
  <p role="alert">Could not load the benchmarks: {error}</p>
{:else if !index}
  <p aria-live="polite">Loading the benchmarks…</p>
{:else}
  {#each index.groups as group (group.id)}
    <section aria-labelledby={group.id}>
      <h2 id={group.id}>{group.name}</h2>
      <ul>
        {#each index.benchmarks.filter((b) => b.group === group.id) as benchmark (benchmark.id)}
          <li>{benchmark.name}</li>
        {/each}
      </ul>
    </section>
  {/each}
{/if}
