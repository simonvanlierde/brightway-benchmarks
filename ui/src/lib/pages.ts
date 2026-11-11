// The pages the masthead and the footer name, shared by the viewer and the static pages.
import { writeView } from "./history";

/** The viewer's own pages, in the masthead. */
export const VIEWER_PAGES = [
  { id: "home", text: "Setup" },
  { id: "explorer", text: "Benchmarks" },
] as const;

/**
 * The static pages: the footer names all. Findings is the masthead's third item; `under` is the
 * masthead item a page belongs to, so a story marks Findings as current (decision 0005).
 */
export const STATIC_PAGES = [
  { id: "findings", text: "Findings", footer: "Findings", path: "findings/", under: "findings" },
  { id: "about", text: "About", footer: "About & privacy", path: "about/", under: undefined },
  {
    id: "solver-choice",
    text: "Solver story",
    footer: "Solver story",
    path: "stories/solver-choice/",
    under: "findings",
  },
  {
    id: "home-heating",
    text: "Heating case",
    footer: "Heating case",
    path: "stories/home-heating/",
    under: "findings",
  },
] as const;

export type StaticPageId = (typeof STATIC_PAGES)[number]["id"];

/** A static page's URL, given the site's root HOME. */
export function staticHref(home: string, id: StaticPageId): string {
  return `${home}${STATIC_PAGES.find((p) => p.id === id)?.path}`;
}

/** A viewer page's URL from a static page, given the site's root HOME. */
export function viewerHref(home: string, id: (typeof VIEWER_PAGES)[number]["id"]): string {
  return id === "home" ? home : `${home}${writeView({ page: id, params: [] })}`;
}
