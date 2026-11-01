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
  s1: "#315bba"
  s2: "#526d91"
  s3: "#7757ac"
  s4: "#416d86"
  s5: "#9b427c"
  s6: "#68618f"
  s7: "#3a6880"
  s8: "#885b8b"
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
  dark-s1: "#91b4ff"
  dark-s2: "#a7bce8"
  dark-s3: "#c2a6f1"
  dark-s4: "#85c0df"
  dark-s5: "#d8c78a"
  dark-s6: "#b8ade3"
  dark-s7: "#8fb2d3"
  dark-s8: "#d6abdd"
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

The primary blue accent anchors links, active navigation, selected platform buttons and solver bars. The pale blue selection wash marks chosen filters, catalogue entries and compatibility rows. Page, rail and panels share one ground (`page`) in each theme, so content reads as a continuous workspace.

Ink, secondary ink and muted text establish hierarchy; line, axis, control and grid colours separate content and support charts. Red and teal label worse and better results, while shift stays neutral. The eight series colours identify environments independently of navigation and status. Dark mode preserves these roles with a dark navy ground and lighter text and series colours.

## Typography

Use the system sans stack for headings, controls and tables. Page titles and the larger Home title share a restrained weight and tight tracking; both use the title tokens above.

Monospace belongs to original identifiers and environment specifications. Measurements use tabular numerals and right-aligned numeric columns. Solver timing values are prominent. Keep explanatory prose within about 68 characters per line where space allows.

## Layout

Breakpoints and sizes live in [ui/src/styles.css](ui/src/styles.css); this section gives the intent.

The compact masthead links Home, Compatibility, Release changes and Benchmark explorer. Home places setup and solver evidence side by side, with a full-width maintainer summary below; setup and solver sections begin on matching rules, and timing columns align within the solver table. As the screen narrows, Compatibility detail moves below its table, the masthead becomes its own scrolling row, and then setup, solver evidence and summary stack into one column.

Compatibility pairs its filterable check table with a selected-detail pane on wide screens. Only Benchmark explorer has a catalogue rail, sticky on wide screens and a disclosure on narrow ones. Filters sit directly above the evidence they control.

On phones, release-change tables reflow into labelled rows. Full measurement tables keep horizontal scrolling in their own focusable region. Charts reduce tick density without dropping keyboard access to any release.

## Elevation & Depth

Use continuous surfaces and one-pixel rules to divide content. Do not add decorative shadows. Charts and selected compatibility details have a single fine frame; controls and data tables belong to the same workspace rather than nested cards.

## Shapes

All corners are square, including controls, charts, selections and detail frames. Use a two-pixel visible focus outline with a two-pixel offset and preserve native inputs. Rules and aligned edges establish structure without rounded or floating cards.

## Components

Primary downloads use accent fill with page-coloured text and the primary-download padding. Data ordering chooses the primary file; other installation files remain links. Pressed platform buttons use solid accent fill with page-coloured text. Chosen direction filters and catalogue entries use the selection wash; active masthead navigation uses an accent underline.

Search fields and selects use the page ground and control stroke. Links thicken their underline on hover. Buttons and catalogue entries use the selection wash on hover; row hover uses a faint selection wash. Native-control and catalogue colour transitions last 150ms only when reduced motion is not requested. All interactive controls retain visible keyboard focus.

Release changes put regressions first, one row per case; improvements group by benchmark with their cases folded. Chart legend entries are buttons that bring one environment forward. A history with two releases shows points without a line. Text is never smaller than 12px.

Benchmark labels use a readable fallback, with original identifiers in detail views and link titles. Ambiguous labels include their identifiers; search accepts either form. Filter counts update together and selections live in the URL. Empty filters and unknown links explain how to recover. Platform controls select a published setup directly. Saved files carry their passing date; smoke calculations and upstream test suites keep separate coverage labels. External project and method links sit in the footer.

## Do's and Don'ts

- Do put each change beside the noise threshold it exceeded.
- Do pair status colours with words and keep categorical series separate from status.
- Do preserve native links, visible keyboard focus and a data table behind every chart.
- Do show original identifiers where a reader needs to reproduce a result.
- Do keep new screens within the same data-driven viewer contract.
- Don't introduce rounded panels or decorative shadows.
- Don't turn current failures or dated installation files into an unsupported passing claim.
