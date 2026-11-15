# 0006. Setup installs; Benchmarks and Findings carry the evidence

- Status: accepted; amended by 0007
- Date: 2026-11-12
- Amends: 0002, 0005

## Context

0002 put the solver comparison and the latest release changes beside the install set on Setup.
0005 then added Findings to the masthead but kept finding cards on Setup and Benchmarks and
footer links to Findings and each story. Setup ended up with six sections that competed with the
install command, and showed the solver claim three ways. A design review scored its minimalism
1 of 4. The write-ups stayed on GitHub, so a reader left the site to see how a finding was
measured.

## Decision

Setup is about installing: the install set, the check grid and a one-line Python summary. A
short "From the benchmarks" list links the evidence: the solver times, the largest release
change each way and the Findings page. The solver comparison, the release changes and the Python
versions table live on Benchmarks, which drops its finding cards for a link to Findings.

`/findings/` renders `docs/findings.md` in full below the headlines, which it groups by the
package section their write-up sits in. A finding's write-up link, in `index.json` too, is an
anchor on that page. A benchmark view that shows a finding names it and links its write-up. The
footer holds the project links (Method, Cite, GitHub, About) and the build only.

## Consequences

A visitor who wants a command sees only what qualifies it; the solver advice is one click away
rather than beside the command. Setup opens on the visitor's own operating system when the
address names none.

The static page budget in `ui/scripts/size.mjs` rises from 20 KB to 28 KB gzipped, as
`/findings/` carries the whole write-up and grows with each one. Relative links in
`docs/findings.md` open on GitHub. The build fails when a finding's `doc` has no heading in
`docs/findings.md`. A story is reached from Findings, About and its finding.
