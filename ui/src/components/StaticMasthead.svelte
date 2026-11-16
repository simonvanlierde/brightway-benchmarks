<script lang="ts">
// The static pages' masthead, with the viewer's search. The benchmarks come from the published index,
// fetched on the first words.
import { tick } from "svelte";
import type { BenchmarkIndex } from "../lib/contract";
import { benchLabel, type View, writeView } from "../lib/history";
import { matchBenchmarks, SiteSearch } from "../lib/site-search.svelte";
import Masthead from "./Masthead.svelte";

let {
  name,
  home,
  links,
}: {
  name: string;
  home: string;
  links: { href: string; text: string; current: boolean }[];
} = $props();

// Words typed before the script loaded stay in the field.
const search = new SiteSearch(
  () => home,
  (globalThis.document?.getElementById("benchmark-search") as HTMLInputElement | null)?.value,
);
let open = $state(false);
let index = $state<BenchmarkIndex>();
let fetched = false;
$effect(() => {
  if (!search.text.trim() || fetched) return;
  fetched = true;
  // The viewer's data folder, relative to the viewer's URL. The viewer checks the file against its schema;
  // here a bad or missing one only leaves the benchmarks out.
  // Not contract.ts's folder(): importing it would bring the schema validators to every static page.
  const base: string = import.meta.env.PUBLIC_DATA_URL ?? "data/";
  const data = new URL(base.endsWith("/") ? base : `${base}/`, new URL(import.meta.env.BASE_URL, location.href));
  fetch(new URL("index.json", data))
    .then((r) => (r.ok ? r.json() : undefined))
    .then((json: BenchmarkIndex | undefined) => {
      if (Array.isArray(json?.benchmarks) && Array.isArray(json.groups)) index = json;
    })
    .catch(() => {});
});
const matching = $derived(matchBenchmarks(index, search.text));
const viewer = (view: View) => `${home}${writeView(view)}`;
const catalogue = viewer({ page: "explorer", params: [] });
</script>

<Masthead
  {name}
  {home}
  {links}
  search={{
    value: search.text,
    open,
    toggle: () => {
      open = !open;
      if (open) tick().then(() => document.getElementById("benchmark-search")?.focus());
    },
    input: (text: string) => (search.text = text),
    submit: (e: SubmitEvent) => {
      const first = matching[0];
      search.submit(e, first && (() => location.assign(viewer({ bench: first.id, params: [] }))));
    },
    results: {
      benchmarks: matching.slice(0, 6).map((b) => {
        const g = index?.groups.find((x) => x.id === b.group);
        return { href: viewer({ bench: b.id, params: [] }), title: index ? benchLabel(index, b) : b.name, detail: g?.label ?? g?.name ?? "" };
      }),
      more: matching.length > 6 ? { count: matching.length, href: viewer({ page: "explorer", params: [], q: search.text.trim() }) } : undefined,
      catalogue: { href: catalogue },
      pages: search.pages.map((h) => ({ href: h.url, title: h.title, detail: h.page, excerpt: h.excerpt })),
      pending: search.pending,
    },
  }}
/>
