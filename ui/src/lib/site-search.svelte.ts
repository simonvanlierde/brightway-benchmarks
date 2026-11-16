// The masthead search, shared by the viewer and the static pages: benchmarks from the index, and the
// sections of Findings, the stories and About from Pagefind. Pagefind's index is written after the
// build (`pnpm build`); `pnpm dev` has none, so the search lists benchmarks only there.
import type { BenchmarkIndex } from "./contract";
import { benchLabel } from "./history";

type Benchmark = BenchmarkIndex["benchmarks"][number];

interface Pagefind {
  options(o: { baseUrl: string }): Promise<void>;
  debouncedSearch(text: string): Promise<{ results: { data(): Promise<PageData> }[] } | null>;
}
interface PageSection {
  url: string;
  title: string;
  excerpt: string;
}
interface PageData extends PageSection {
  meta: { title: string };
  sub_results: PageSection[];
}
export type PageHit = PageSection & { page: string };

let pagefind: Promise<Pagefind | undefined> | undefined;
// A runtime URL: the bundler must not look for Pagefind, which is written after it runs.
const loadPagefind = (url: string): Promise<Pagefind> => import(/* @vite-ignore */ url);

/** Every word of TEXT must appear in the benchmark's name, label or package, in any order. */
export function matchBenchmarks(index: BenchmarkIndex | undefined, text: string): Benchmark[] {
  const words = text.toLowerCase().split(/\s+/).filter(Boolean);
  return (
    index?.benchmarks.filter((b) => {
      const g = index.groups.find((x) => x.id === b.group);
      const haystack = `${b.name} ${benchLabel(index, b)} ${g?.label ?? ""} ${g?.name ?? ""}`.toLowerCase();
      return words.every((w) => haystack.includes(w));
    }) ?? []
  );
}

/** The words in the field and Pagefind's hits for them. Construct it while a component initialises. */
export class SiteSearch {
  text = $state("");
  // The hits name the words they answer. While Pagefind works on new words the last hits stay in view,
  // marked pending, but Enter waits for the answer.
  #pages = $state<{ text: string; hits: PageHit[] }>({ text: "", hits: [] });
  #enterFor = $state("");
  readonly pages = $derived(this.#pages.hits);
  readonly pending = $derived(this.#pages.text !== this.text.trim());

  /** HOME gives the site's root, which Pagefind's URLs are relative to. */
  constructor(home: () => string, text = "") {
    this.text = text;
    $effect(() => {
      const words = this.text.trim();
      if (!words) return;
      pagefind ??= loadPagefind(`${import.meta.env.BASE_URL}pagefind/pagefind.js`)
        .then(async (pf) => {
          await pf.options({ baseUrl: home() });
          return pf;
        })
        .catch(() => undefined);
      let stale = false;
      pagefind.then(async (pf) => {
        let hits: PageHit[] = [];
        // Without an index (`pnpm dev`) or after a failed fetch, the pages have nothing to add.
        try {
          const found = pf ? await pf.debouncedSearch(words) : { results: [] };
          if (!found) return; // superseded by newer words
          const pages = await Promise.all(found.results.slice(0, 5).map((r) => r.data()));
          // A page's best sections, not the page itself, when it has headings to land on.
          hits = pages
            .flatMap((d) =>
              (d.sub_results.length ? d.sub_results.slice(0, 3) : [d]).map((x) => ({ ...x, page: d.meta.title })),
            )
            .slice(0, 6);
        } catch {}
        if (!stale) this.#pages = { text: words, hits };
      });
      return () => {
        stale = true;
      };
    });
    $effect(() => {
      if (!this.#enterFor) return;
      // Typing on cancels the pending Enter.
      if (this.#enterFor !== this.text.trim()) this.#enterFor = "";
      else if (!this.pending) {
        this.#enterFor = "";
        if (this.#pages.hits[0]) location.href = this.#pages.hits[0].url;
      }
    });
  }

  /** Enter in the field: OPEN the first benchmark when one matches, else the first page hit once Pagefind has the words. */
  submit(e: SubmitEvent, open?: () => void) {
    e.preventDefault();
    if (open) open();
    else this.#enterFor = this.text.trim();
  }
}
