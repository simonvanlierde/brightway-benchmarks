---
name: Benchmark viewer
description: A scientific evidence workspace for release histories and measured changes
colors:
  page: "#f5f6fa"
  surface: "#ffffff"
  navigation: "#edf0f8"
  text: "#20283d"
  secondary-text: "#4c576d"
  muted-text: "#637087"
  accent: "#3d4fa8"
  selection: "#dfe5fa"
  worse: "#b03045"
  better: "#006c5c"
  dark-page: "#151a26"
  dark-surface: "#1b2231"
  dark-navigation: "#1d263b"
  dark-text: "#edf0f8"
  dark-accent: "#b3c1ff"
typography:
  body:
    fontFamily: "system-ui, -apple-system, Segoe UI, sans-serif"
    fontSize: "15px"
    lineHeight: 1.55
  title:
    fontFamily: "system-ui, -apple-system, Segoe UI, sans-serif"
    fontSize: "clamp(1.7rem, 2.7vw, 2.4rem)"
    fontWeight: 650
    letterSpacing: "-0.035em"
  home-title:
    fontFamily: "system-ui, -apple-system, Segoe UI, sans-serif"
    fontSize: "clamp(1.7rem, 2.5vw, 2.25rem)"
    fontWeight: 650
    letterSpacing: "-0.035em"
rounded:
  control: "7px"
  panel: "12px"
  chart: "14px"
spacing:
  compact: "6px"
  field: "18px"
  desktop-content: "40px"
components:
  selected-navigation:
    backgroundColor: "{colors.selection}"
    textColor: "{colors.accent}"
  chart:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.chart}"
  primary-download:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.surface}"
    rounded: "{rounded.control}"
    padding: "9px 14px"
  selected-platform:
    backgroundColor: "{colors.selection}"
    textColor: "{colors.accent}"
    rounded: "{rounded.control}"
    padding: "7px 18px"
---

## Overview

A working screen for inspecting evidence. The homepage leads with a tested setup and its coverage; compact evidence for both regressions and improvements sits beside it. Changes and their uncertainty lead the dedicated maintainer views. Avoid decorative metrics or claims that the data does not support.

## Colors

The indigo navigation ground separates the catalogue from the evidence workspace. Selection uses indigo, while red and teal identify worse and better results. Series use a separate fixed categorical palette in `ui/src/styles.css`; outlined symbols distinguish coincident lines. Dark mode keeps the same roles with lighter text and series colours.

## Typography

Use the system sans stack for readable controls and dense tables. Titles carry the page hierarchy through size and weight. Monospace belongs to original identifiers and environment specifications. Measurements use tabular numerals. Keep explanatory prose within 68 characters per line where space allows.

## Layout

A compact masthead links Home, Compatibility, Release changes and Benchmark explorer. Home uses a broad setup-and-solver column beside a smaller change summary. Compatibility pairs a filterable check table with a 370px selected detail pane. At 75rem and below, the detail stacks below the table and the masthead navigation moves to a separate scrolling row. Selecting a check reveals its detail pane. At 55rem and below, Home stacks the change summary below the setup and solver evidence.

Only the benchmark explorer has a catalogue rail. At 60rem and above, it is 16.5rem wide and scrolls independently. Below that width it becomes a disclosure. Release-change filters sit directly above the changes they control; benchmark parameters sit directly above the chart.

At 39rem and below, change tables reflow into labelled rows and installation details stack into one column. Full measurement tables retain horizontal scrolling in their own focusable region. Charts reduce tick density without dropping keyboard access to any release.

## Elevation & Depth

Use surfaces and one-pixel borders to separate content. Avoid decorative shadows. A chart has one frame; the controls and data table belong to the same workspace rather than nested cards.

## Shapes

Controls use the control radius. Compatibility panels use the panel radius; setup, summary and chart frames use the chart radius. Use a two-pixel visible focus outline and standard native inputs.

## Components

The primary download uses the accent background and surface-coloured text, with 9px by 14px padding and a 40px minimum height. Data ordering chooses its file; other installation files remain links. Platform choices use selection fill with accent text when pressed. Native controls share the visible focus outline.

Benchmark labels use a readable fallback, with original identifiers in the detail view and link titles. Ambiguous labels include their identifiers. Search accepts either form. Package and direction filters update their counts together, and their selections live in the URL. Empty filters and unknown benchmark links explain how to recover. Platform controls select a published setup directly, without a wizard. Saved installation files carry their passing date; a current failure never becomes a passing claim. Smoke calculations and upstream test suites keep separate coverage labels. External project and method links sit in the footer.

## Do's and Don'ts

- Put each change beside the noise threshold it exceeded.
- Pair status colours with words; keep categorical series separate from status.
- Preserve native links, keyboard access and a data table behind every chart.
- Show original identifiers where a reader needs to reproduce a result.
- Keep new screens within the same data-driven viewer contract.
