---
name: Benchmark viewer
description: A scientific evidence workspace for tested setups and measured changes
colors:
  page: "#f8f9fc"
  ink: "#172b65"
  ink-2: "#42547d"
  muted: "#536084"
  grid: "#e3e8f3"
  axis: "#8d9cc0"
  line: "#bfc9e4"
  control: "#536084"
  accent: "#1636b9"
  accent-wash: "#dce5fb"
  worse: "#a13236"
  better: "#006c65"
  shift: "#42547d"
  s1: "#2a78d6"
  s2: "#d9582a"
  s3: "#12907a"
  s4: "#a87500"
  s5: "#cc4f82"
  s6: "#2f7d1f"
  s7: "#6250d6"
  s8: "#7d7a00"
  dark-page: "#141d32"
  dark-ink: "#f8f9fc"
  dark-ink-2: "#c7d2ed"
  dark-muted: "#aab9d8"
  dark-grid: "#2a3755"
  dark-axis: "#6b7fa9"
  dark-line: "#3d4d70"
  dark-control: "#9aadd2"
  dark-accent: "#b3c5ff"
  dark-accent-wash: "#2c3d67"
  dark-worse: "#ffafb0"
  dark-better: "#74cfc3"
  dark-shift: "#aab9d8"
  dark-s1: "#3987e5"
  dark-s2: "#d95926"
  dark-s3: "#199e70"
  dark-s4: "#c98500"
  dark-s5: "#d55181"
  dark-s6: "#2d9d1f"
  dark-s7: "#9085e9"
  dark-s8: "#938f0f"
typography:
  body:
    fontFamily: "system-ui, -apple-system, Segoe UI, sans-serif"
    fontSize: "15px"
    lineHeight: 1.55
  title:
    fontFamily: "system-ui, -apple-system, Segoe UI, sans-serif"
    fontSize: "clamp(1.7rem, 2.7vw, 2.4rem)"
    fontWeight: 650
    lineHeight: 1.25
    letterSpacing: "-0.035em"
  home-title:
    fontFamily: "system-ui, -apple-system, Segoe UI, sans-serif"
    fontSize: "clamp(2rem, 3.5vw, 3.4rem)"
    fontWeight: 650
    lineHeight: 1.25
    letterSpacing: "-0.035em"
  mono:
    fontFamily: "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"
    fontSize: "0.875em"
rounded:
  control: "0"
  panel: "0"
  chart: "0"
spacing:
  compact: "6px"
  field: "18px"
  desktop-content: "40px"
components:
  selected-navigation:
    backgroundColor: "{colors.accent-wash}"
    textColor: "{colors.accent}"
    rounded: "{rounded.control}"
  chart:
    backgroundColor: "{colors.page}"
    rounded: "{rounded.chart}"
    padding: "24px 24px 20px"
  primary-download:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.page}"
    rounded: "{rounded.control}"
    padding: "9px 14px"
  selected-platform:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.page}"
    rounded: "{rounded.control}"
    padding: "7px 18px"
---

## Overview

Square geometry and aligned measurement columns give the viewer a precise reading order. Cool white and dark navy grounds run continuously through the workspace; fine rules separate evidence without floating panels. System sans typography keeps dense controls and tables readable.

## Colors

The primary blue accent anchors links, active navigation, selected controls and solver bars. The pale blue selection wash marks chosen filters, catalogue entries and compatibility rows. Page, rail and panels share one ground (`page`) in each theme, so content reads as a continuous workspace.

Ink, secondary ink and muted text establish hierarchy; line, axis, control and grid colours separate content and support charts. Red and teal label worse and better results, while shift stays neutral. The eight series colours identify environments independently of navigation and status. Each environment label keeps its colour slot on every chart, and a story bar takes the slot of the solver it shows. They are spread in hue (blue, orange, teal, amber, magenta, green, violet, olive) and were checked with the data-viz palette validator for neighbouring-pair separation under colour-vision simulation, normal-vision separation and 3:1 contrast on the page in both themes. Past three series they are not safe for all-pairs forms such as scatter, so lines also differ by marker shape and carry end-of-line names where the chart is wide enough. Dark mode preserves these roles with a dark navy ground, lighter text and series colours re-tuned for contrast on that ground.

## Typography

Use the system sans stack for headings, controls and tables. Page titles and the larger Home title share a restrained weight and tight tracking; both use the title tokens above.

Below the titles, text uses seven roles on a 15px root: meta 0.8rem, 12px (dates, build ids, captions, labels), data 0.875rem (tables, buttons, navigation, catalogue), evidence 0.9375rem, 14px (what a reader acts on: change evidence, check-grid headers, install notes, finding text, parameter notes and the chart's reading guide), control 0.9375rem (selects and fixed parameter values), body 1rem (ledes, changes, benchmark names), subhead 1.35rem (sections inside a view and the selected-check pane) and section 1.25rem (Setup's and Benchmarks' sections). Weight separates roles of the same size; parameter names are muted so their values lead.

Monospace belongs to original identifiers and environment specifications. Measurements use tabular numerals and right-aligned numeric columns. Solver timing values are prominent.

Story charts sit between horizontal rules, with the evidence link after the rows. On hover-capable devices, a row takes the selection wash to connect its label, value and bar without motion.

Static reading pages use 1.0625rem body text with 1.7 line height and a 65ch prose measure. Section headings have more space above than below; headings balance and prose wraps with `pretty`. Charts and tables retain the full page width.

## Layout

Breakpoints and sizes live in [ui/src/styles.css](ui/src/styles.css); this section gives the intent.

The compact masthead links Setup, Benchmarks and Findings (decision 0005) and holds benchmark search and a sun/moon theme toggle. The Findings page groups the headline findings by package in a two-column ledger (package left, findings right), then renders the write-ups of `docs/findings.md` below (decision 0006); a story marks Findings as the current item, and the Benchmarks intro links it. A benchmark view that shows a finding names it in a pale-blue band under its description. Method, Cite, GitHub, About and build identity sit in the footer, the build id on its own row on phones; check freshness sits beside Checks. Setup is about installing (decision 0006): the title and the install column (operating-system, Python and package-manager selects, a one-line Python summary, check results and the install command) on the left; the check grid and a quiet "From the benchmarks" list on the right, divided by a hairline. That list's few lines (the solver times, the largest release change each way, the Findings page) are the way into the evidence, which lives on Benchmarks. As the screen narrows, the masthead becomes its own scrolling row that keeps the current page in view, and the two columns stack.

Benchmarks content shares one measure of 72rem, so the toolbar, findings, tables and chart end on one right edge; static pages share a centred 46rem frame, with prose capped at 65ch and tables spanning the frame. Narrow static-page mastheads give navigation its own row so every link stays visible without JavaScript. Across machines (decision 0007) sits under Benchmarks with the catalogue beside it: one table per comparison, a row group per choice headed by its summary, one row per machine with its interval drawn on a log scale around a line at 1, teal when clearly faster, red when clearly slower, muted otherwise; on phones each machine becomes a block with the interval full width. Each page's main content fits a 1440 by 900 laptop screen: the install command and its result line on Setup, the solver comparison on Benchmarks, the whole chart on a benchmark. A browser test checks it.

Only Benchmarks has a catalogue rail, sticky on wide screens and a disclosure on narrow ones; inside it each package is a collapsible group and the current benchmark's group is open. Filters sit directly above the evidence they control. Parameter explanations stay under their controls on desktop and use a disclosure on phones.

On phones, release-change tables reflow into labelled rows. Full measurement tables keep horizontal scrolling in their own focusable region. Charts reduce tick density without dropping keyboard access to any release.

## Elevation & Depth

Use continuous surfaces and one-pixel rules to divide content. Do not add decorative shadows. Charts and selected compatibility details have a single fine frame; controls and data tables belong to the same workspace rather than nested cards.

## Shapes

All corners are square, including controls, charts, selections and detail frames. Use a two-pixel visible focus outline with a two-pixel offset and preserve native inputs. Rules and aligned edges establish structure without rounded or floating cards.

## Components

Primary downloads use accent fill with page-coloured text and the primary-download padding. Data ordering chooses the primary file; other installation files remain links. Chosen direction filters and catalogue entries use the selection wash; active masthead navigation uses an accent underline.

Search fields and selects use the page ground and control stroke. Links thicken their underline on hover. Buttons and catalogue entries use the selection wash on hover; row hover uses a faint selection wash. Native-control and catalogue colour transitions last 150ms only when reduced motion is not requested. All interactive controls retain visible keyboard focus.

Release changes put regressions first, one row per benchmark with several environments folded; improvements fold behind their count and group by benchmark with their cases folded. Chart legend entries are buttons that bring one environment forward. A history with two releases shows points without a line, and with three or fewer each environment sits a little apart so equal values stay visible. Commits that are not releases draw faint, and the explorer counts them under its changes. Setup puts the command's check results (status first) and coverage caveats before Copy, and a failed upstream suite's note after it; the files, package versions and Copy latest fold under "What's in this set". Phones list checks for the selected platform; desktop keeps the comparison grid with its platform column pinned and a conditional scroll hint. Text is never smaller than 12px. On phones disclosure summaries, footer links, install file links and the masthead's page links are at least 44px high and release-change benchmark names carry 8px of padding above and below (other controls keep their own sizes), the masthead is one row up to 60rem wide with the search behind an icon, and benchmark parameters stack at full width.

The explorer says what the benchmark measures under its title. Desktop explains each parameter under its control; phones keep the controls visible and put explanations under “Parameter details”. New uv projects have an optional copyable setup sequence. Copy latest has a 44px target and the Copy button's border, weight and size. A scroll region takes keyboard focus and shows a shaded edge only while it has something to scroll.

Benchmark labels use a readable fallback, with original identifiers in detail views and link titles. Ambiguous labels include their identifiers; search accepts either form. Filter counts update together and selections live in the URL. Empty filters and unknown links explain how to recover. Labelled native selects choose operating system, Python and package manager. Changing manager preserves Python. The command’s date and file links share a compact row; project instructions and package versions expand on demand. The theme follows the system until a visitor chooses light or dark, and that choice is remembered. Saved files carry their passing date; smoke calculations and upstream test suites keep separate coverage labels. External project and method links sit in the footer.

## Do's and Don'ts

- Do put each change beside the noise threshold it exceeded.
- Do pair status colours with words and keep categorical series separate from status.
- Do preserve native links, visible keyboard focus and a data table behind every chart.
- Do show original identifiers where a reader needs to reproduce a result.
- Do keep new screens within the same data-driven viewer contract.
- Don't introduce rounded panels or decorative shadows.
- Don't turn current failures or dated installation files into an unsupported passing claim.
