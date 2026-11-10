// What the shown environments run, from the index's environment records: no fetching, no DOM.
import type { BenchmarkIndex } from "./contract";
import type { Line } from "./history";

export interface EnvNote {
  name: string;
  text: string;
  url: string | undefined;
}

const byId = (index: BenchmarkIndex | undefined) => new Map(index?.environments.map((e) => [e.id, e]));

/** What a shown environment runs, where the data explains it (an experimental solver, say): one entry each. */
export function envNotes(index: BenchmarkIndex | undefined, shown: Line[]): EnvNote[] {
  const envs = byId(index);
  const out = new Map<string, EnvNote>();
  for (const l of shown) {
    const env = envs.get(l.env);
    if (!env?.description || out.has(env.description)) continue;
    const name = env.label ?? env.name;
    const text = env.description.startsWith(`${name}: `) ? env.description.slice(name.length + 2) : env.description;
    out.set(env.description, { name, text, url: env.url ?? undefined });
  }
  return [...out.values()];
}

/** Each other linked solver once, apart from those NOTES already link: "UMFPACK" and "UMFPACK, MKL" share a page. */
export function solverLinks(
  index: BenchmarkIndex | undefined,
  shown: Line[],
  notes: EnvNote[],
): { url: string; label: string }[] {
  const envs = byId(index);
  const noted = new Set(notes.map((n) => n.url));
  const out = new Map<string, string>();
  for (const l of shown) {
    const env = envs.get(l.env);
    if (env?.url && !noted.has(env.url) && !out.has(env.url))
      out.set(env.url, (env.label ?? env.name).split(/,| on | · /)[0] ?? env.name);
  }
  return [...out].map(([url, label]) => ({ url, label }));
}
