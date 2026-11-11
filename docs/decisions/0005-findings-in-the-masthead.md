# 0005. Findings in the masthead

- Status: accepted
- Date: 2026-11-11
- Supersedes: 0004

## Context

0004 kept stories out of the masthead and linked them from the footer, About and a line on each
page. More stories are planned: one on pizza, an AI run, and how the Brightway packages fit
together. Findings and stories already said the same claim under two names in two places: the
finding cards on Setup and Benchmarks, and a story page reached only from the footer. The static
pages already marked themselves in the masthead, so it had in effect grown a third item.

## Decision

The masthead has three items: Setup, Benchmarks and Findings. Findings opens `/findings/`, a
static page that lists every entry of `benchmarks/findings.toml` with its viewer view, its
write-up in `docs/findings.md` and, where it has one, its story. A story is the long form of a
finding: the finding names it with `story = "<slug>"`, and on a story Findings is the current
item. Story URLs stay `/stories/<slug>/`, so shared links keep working.

The finding cards on Setup and Benchmarks stay as short previews with one link to all findings.
The footer and About keep their links.

0004's other rules hold, for `/findings/` as for stories:

- Each page has its own preview image and description.
- Every chart or number links to the exact viewer view, as a URL the viewer reads back
  (`viewerHref` in `ui/src/lib/story-links.ts`).
- Numbers come only from published results or `benchmarks/findings.toml`. A framing the
  published data does not cover is left out, or labelled as an estimate.

## Consequences

A new story needs a finding to hang from, or it gets one. `scripts/export_ui.py` fails when a
finding's `story` has no page, and when its `params` skip or reorder an axis, as `/findings/`
builds its links by position. A finding a story tells before its benchmarks publish may leave
out `group`, `benchmark` and `params`: `/findings/` lists it and the viewer does not. Story
numbers can still drift from the data, as the export does not read them. Each new page adds a
sitemap entry and a preview image to `pnpm assets`.
