# 0006. Findings carries the write-ups; Setup and the footer drop what it reaches

- Status: accepted
- Date: 2026-11-12
- Amends: 0005

## Context

0005 put Findings in the masthead but kept everything that led to findings before it: finding
cards on Setup and Benchmarks, and footer links to Findings and each story. Setup then showed
the same claims three ways (the solver table, the cards, the masthead), and the footer grew with
every story. The write-ups stayed on GitHub, so a reader left the site to see how a finding was
measured.

## Decision

`/findings/` renders `docs/findings.md` in full below the headlines, which it groups by the
package section their write-up sits in. A finding's write-up link, in `index.json` too, is an
anchor on that page. Setup has no finding cards; Benchmarks keeps them as its overview. The
footer holds the project links (Method, Cite, GitHub, About) and the build only. A benchmark view
that shows a finding names it and links its write-up.

## Consequences

The static page budget in `ui/scripts/size.mjs` rises from 20 KB to 28 KB gzipped, as
`/findings/` carries the whole write-up and grows with each one. Relative links in
`docs/findings.md` open on GitHub. The build fails when a finding's `doc` has no heading in
`docs/findings.md`. A story is reached from Findings, About and the line beside its evidence.
