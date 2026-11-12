<script lang="ts">
// The viewer's masthead and the static pages' one. The static pages render it without script:
// their search is a form that opens the Benchmarks page.
import LogoMark from "./LogoMark.svelte";

interface Hit {
  href: string;
  title: string;
  detail: string;
  excerpt?: string;
  onclick?: (e: MouseEvent) => void;
}

interface NavLink {
  href: string;
  text: string;
  current: boolean;
  onclick?: (e: MouseEvent) => void;
}

let {
  name,
  home,
  links,
  nav = $bindable(),
  onbrand,
  search,
}: {
  name: string;
  home: string;
  links: NavLink[];
  nav?: HTMLElement | undefined;
  onbrand?: (e: MouseEvent) => void;
  /** Present in the viewer: a live search field behind a toggle. Absent on a static page. */
  search?: {
    value: string;
    open: boolean;
    toggle: () => void;
    input: (text: string) => void;
    submit: (e: SubmitEvent) => void;
    results?: {
      benchmarks: Hit[];
      more?: { count: number; href: string; onclick: (e: MouseEvent) => void } | undefined;
      pages: Hit[];
    };
  };
} = $props();

// Results show while the search has focus; Escape hides them until the next keystroke.
let dismissed = $state(false);
let form = $state<HTMLFormElement>();
function keys(e: KeyboardEvent) {
  if (e.key === "Escape") {
    dismissed = true;
    document.getElementById("benchmark-search")?.focus();
    return;
  }
  if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
  const stops = [...(form?.querySelectorAll<HTMLElement>("#benchmark-search, .search-results a") ?? [])];
  const at = stops.indexOf(document.activeElement as HTMLElement);
  const next = stops[Math.max(0, Math.min(stops.length - 1, at + (e.key === "ArrowDown" ? 1 : -1)))];
  if (next) {
    e.preventDefault();
    next.focus();
  }
}
// A picked result leaves the search, so its list closes.
function picked(e: MouseEvent, hit: { onclick?: (e: MouseEvent) => void }) {
  hit.onclick?.(e);
  (document.activeElement as HTMLElement | null)?.blur();
}
</script>

<header class="top">
  <div class="top-inner">
    {#if search}
      <h1><a href={home} onclick={onbrand}><LogoMark size={24} /><span class="brand-name">{name}</span></a></h1>
    {:else}
      <a class="static-brand" href={home}><LogoMark size={24} /><span class="brand-name">{name}</span></a>
    {/if}
    <nav class="primary-nav" aria-label="Main" bind:this={nav}>
      {#each links as link (link.href)}
        <a href={link.href} data-text={link.text} aria-current={link.current ? "page" : undefined} onclick={link.onclick}>{link.text}</a>
      {/each}
    </nav>
    {#if search}
      <button type="button" class="search-toggle" aria-label="Show the search" aria-expanded={search.open} aria-controls="masthead-search" onclick={search.toggle}>
        {@render magnifier()}
      </button>
      <!-- svelte-ignore a11y_no_noninteractive_element_interactions: arrow keys move between the field and its results -->
      <form class="masthead-search" id="masthead-search" class:open={search.open} role="search" onsubmit={search.submit} onkeydown={keys} bind:this={form}>
        <label for="benchmark-search">Search</label>
        <input id="benchmark-search" type="search" autocomplete="off" aria-describedby="search-count" value={search.value} oninput={(e) => { dismissed = false; search.input(e.currentTarget.value); }} placeholder="Benchmarks and findings" />
        {#if search.results && search.value.trim()}
          {@const r = search.results}
          {@const total = r.benchmarks.length + r.pages.length}
          <div class="search-results" class:dismissed>
            <p class="sr" id="search-count" role="status">{total ? `${r.more?.count ?? r.benchmarks.length} benchmarks, ${r.pages.length} sections. Arrow down to the results.` : "No results"}</p>
            {#if r.benchmarks.length}
              <h2>Benchmarks</h2>
              <ul>
                {#each r.benchmarks as hit (hit.href)}
                  <li><a href={hit.href} onclick={(e) => picked(e, hit)}>{hit.title}<span class="hit-detail">{hit.detail}</span></a></li>
                {/each}
                {#if r.more}{@const more = r.more}<li><a class="hit-more" href={more.href} onclick={(e) => picked(e, more)}>All {more.count} in the catalogue</a></li>{/if}
              </ul>
            {/if}
            {#if r.pages.length}
              <h2>Findings and pages</h2>
              <ul>
                {#each r.pages as hit (hit.href)}
                  <!-- Pagefind's excerpt: text from this site's own pages, with the matches in <mark>. -->
                  <li><a href={hit.href} onclick={(e) => picked(e, hit)}>{hit.title}{#if hit.detail !== hit.title}<span class="hit-detail">{hit.detail}</span>{/if}{#if hit.excerpt}<span class="hit-excerpt">{@html hit.excerpt}</span>{/if}</a></li>
                {/each}
              </ul>
            {/if}
            {#if !total}<p class="hit-none">Nothing matches “{search.value.trim()}”.</p>{/if}
          </div>
        {/if}
      </form>
    {:else}
      <a class="search-toggle" href="#masthead-search" aria-label="Show the search">
        {@render magnifier()}
      </a>
      <!-- No script here: the search opens the viewer with its words in the field and their results open. -->
      <form class="masthead-search" id="masthead-search" role="search" action={home} method="get">
        <input type="hidden" name="page" value="explorer" />
        <label for="benchmark-search">Search</label>
        <input id="benchmark-search" type="search" name="q" placeholder="Benchmarks and findings" />
      </form>
    {/if}
    <button type="button" class="theme-toggle" data-theme-toggle aria-label="Switch to dark theme" title="Switch to dark theme">
      <svg data-theme-icon="moon" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M20.8 13A9 9 0 0 1 11 3.2 9 9 0 1 0 20.8 13Z"/></svg>
      <svg data-theme-icon="sun" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" aria-hidden="true"><circle cx="12" cy="12" r="4"/><path d="M12 2v2m0 16v2M2 12h2m16 0h2M5 5l1.5 1.5m11 11L19 19M5 19l1.5-1.5m11-11L19 5"/></svg>
    </button>
  </div>
</header>

{#snippet magnifier()}
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" aria-hidden="true"><circle cx="11" cy="11" r="6.5"/><path d="m16 16 4.5 4.5"/></svg>
{/snippet}
