import { type View, writeView } from "./history";

/** The viewer's address for one benchmark view, from the site root HOME. PARAMS are the labels the viewer shows, one per axis. */
export function viewerHref(home: string, group: string, bench: string, params: string[]): string {
  const view: View = { page: "explorer", group, bench, params };
  return `${home}${writeView(view)}`;
}
