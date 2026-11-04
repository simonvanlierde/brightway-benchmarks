# 0004. Stories outside the masthead

- Status: accepted
- Date: 2026-11-03
- Amends: 0003, the two pages of the masthead

## Context

0003 gave the site two pages, Setup and Benchmarks. Both are tools: they answer a question you
bring. Some findings need a short account that a practitioner can read, share and check, such as
why the installed solver changes one score from 2.6 s to 28 s. That account does not fit a
tool page, and a third masthead page would split the navigation 0003 simplified.

## Decision

A story is a static Astro page at `/stories/<slug>`, built like `about.astro` and held to the
20 KB budget for static pages. Stories stay out of the masthead. The footer, About, one line
on Benchmarks and a line beside the evidence a story explains on Setup link to them.

- Each story has its own preview image and description.
- Every chart or number on a story links to the exact viewer view, as a URL the viewer reads
  back (`viewerHref` in `ui/src/lib/story-links.ts`).
- Numbers come only from published results or `benchmarks/findings.toml`. A framing the
  published data does not cover is left out, or labelled as an estimate.

## Consequences

The masthead stays at two pages. A story's numbers can drift from the data: the export does not
check them, so a story needs a look when its benchmarks or findings change. Each new story adds
a sitemap entry and a preview image to `pnpm assets`.
