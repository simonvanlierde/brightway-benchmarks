<script lang="ts">
import type { Guidance } from "../lib/contract";
import { format } from "../lib/history";

let { comparison, story }: { comparison: NonNullable<Guidance["solverComparison"]>; story?: string } = $props();
const largest = $derived(Math.max(0, ...comparison.rows.map((r) => r.value)));
</script>

<section class="solver-evidence" id="solvers" aria-labelledby="solver-heading">
  <h2 id="solver-heading">{comparison.title}</h2>
  <p>{comparison.context}</p>
  <table><caption>Follow a solver to its benchmark.</caption><thead><tr><th scope="col">Solver</th><th scope="col" class="solver-bar-column"><span class="sr">Relative time</span></th><th scope="col" class="num">Time</th></tr></thead><tbody>{#each comparison.rows as row (row.label)}<tr><th scope="row"><a href={row.href}>{row.label}</a></th><td class="solver-bar-column"><div class="solver-track" aria-hidden="true"><span style:width={`${largest > 0 ? (row.value / largest) * 100 : 0}%`}></span></div></td><td class="num">{format(row.value, row.unit)}</td></tr>{/each}</tbody></table>
  {#if story}<p class="story-link">On the real ecoinvent 3.12 matrix, the factorization alone takes 3.66 s with SuperLU and 0.66 s with conda-forge UMFPACK. <a href={story}>The story shows what to install</a>.</p>{/if}
  {#if comparison.note}<p class="measurement-note">{comparison.note}</p>{/if}
</section>
