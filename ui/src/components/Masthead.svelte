<script lang="ts">
// The viewer's masthead and the static pages' one. The static pages render it without script:
// their search is a form that opens the Benchmarks page.
import LogoMark from "./LogoMark.svelte";

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
  };
} = $props();
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
        <a href={link.href} aria-current={link.current ? "page" : undefined} onclick={link.onclick}>{link.text}</a>
      {/each}
    </nav>
    {#if search}
      <button type="button" class="search-toggle" aria-label="Show the benchmark search" aria-expanded={search.open} aria-controls="masthead-search" onclick={search.toggle}>
        {@render magnifier()}
      </button>
      <form class="masthead-search" id="masthead-search" class:open={search.open} role="search" onsubmit={search.submit}>
        <label for="benchmark-search">Find a benchmark</label>
        <input id="benchmark-search" type="search" value={search.value} oninput={(e) => search.input(e.currentTarget.value)} placeholder="Name or package" />
      </form>
    {:else}
      <a class="search-toggle" href="#masthead-search" aria-label="Show the benchmark search">
        {@render magnifier()}
      </a>
      <!-- No script here: the search opens the Benchmarks page with its words in the catalogue filter. -->
      <form class="masthead-search" id="masthead-search" role="search" action={home} method="get">
        <input type="hidden" name="page" value="explorer" />
        <label for="benchmark-search">Find a benchmark</label>
        <input id="benchmark-search" type="search" name="q" placeholder="Name or package" />
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
