// Generates static branding assets for the Brightway Benchmarks viewer:
// - ui/public/favicon.svg (Scalable vector icon)
// - ui/public/favicon.ico (Standard 32x32 multi-platform favicon)
// - ui/public/apple-touch-icon.png (180x180 for iOS/mobile bookmarks)
// - ui/public/og.png (1200x630 Open Graph card for social sharing)
// - ui/public/story-solver-choice.png (1200x630 card for the solver story)
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "@playwright/test";

const __dirname = dirname(fileURLToPath(import.meta.url));
const publicDir = join(__dirname, "../public");
mkdirSync(publicDir, { recursive: true });

// 1. Scalable SVG Favicon: Fuses benchmark columns with the Brightway Delaunay leaf,
// dynamically adapting between light and dark browser themes via CSS media queries.
const faviconSvg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32" width="32" height="32">
  <title>Brightway Benchmarks</title>
  <style>
    :root {
      --bg: #f8f9fc;
      --grid: #e3e8f3;
      --line: #bfc9e4;
      --axis: #8d9cc0;
      --s1: #315bba;
      --better: #006c65;
      --ink: #172b65;
    }
    @media (prefers-color-scheme: dark) {
      :root {
        --bg: #141d32;
        --grid: #2a3755;
        --line: #3d4d70;
        --axis: #6b7fa9;
        --s1: #91b4ff;
        --better: #74cfc3;
        --ink: #f8f9fc;
      }
    }
    .bg { fill: var(--bg); }
    .frame { stroke: var(--grid); }
    .baseline { stroke: var(--line); }
    .bar-axis { fill: var(--axis); }
    .bar-s1 { fill: var(--s1); }
    .leaf-facet { fill: var(--better); }
    .leaf-wire { stroke: var(--ink); }
    .apex-node { fill: var(--ink); }
  </style>
  <rect class="bg" width="32" height="32" />
  <rect class="frame" x="0.5" y="0.5" width="31" height="31" fill="none" stroke-width="1" />
  <!-- Benchmark baseline -->
  <line class="baseline" x1="4" y1="26" x2="28" y2="26" stroke-width="1.2" />
  <!-- Benchmark Bar 1: SuperLU baseline (grey-blue) -->
  <rect class="bar-axis" x="5.5" y="18" width="4.5" height="8" />
  <!-- Benchmark Bar 2: PyPardiso (series blue) -->
  <rect class="bar-s1" x="12" y="12" width="4.5" height="14" />
  <!-- Position 3: Brightway Triangulated Leaf (optimal) -->
  <g class="leaf-facet">
    <polygon points="18.5,25.5 15.5,18 20,18" fill-opacity="0.35" />
    <polygon points="18.5,25.5 20,18 25,22" fill-opacity="0.25" />
    <polygon points="20,18 25,22 27.5,16" fill-opacity="0.45" />
    <polygon points="15.5,18 17.5,11 22,12" fill-opacity="0.5" />
    <polygon points="15.5,18 20,18 22,12" fill-opacity="0.3" />
    <polygon points="20,18 22,12 27.5,16" fill-opacity="0.4" />
    <polygon points="22,12 27.5,16 27,10" fill-opacity="0.6" />
    <polygon points="17.5,11 25.5,5 22,12" fill-opacity="0.75" />
    <polygon points="22,12 25.5,5 27,10" fill-opacity="0.85" />
  </g>
  <!-- Leaf contour and triangulation wireframe (Brightway signature) -->
  <g class="leaf-wire" stroke-width="0.75" stroke-linecap="round" stroke-linejoin="round" fill="none">
    <path d="M 18.5 25.5 C 14.5 18 17 9 25.5 5 C 29 11 29 21 18.5 25.5 Z" stroke-width="1.1" />
    <line x1="18.5" y1="25.5" x2="25.5" y2="5" stroke-width="1.2" />
    <line x1="15.5" y1="18" x2="20" y2="18" />
    <line x1="20" y1="18" x2="27.5" y2="16" />
    <line x1="17.5" y1="11" x2="22" y2="12" />
    <line x1="22" y1="12" x2="27" y2="10" />
    <line x1="18.5" y1="25.5" x2="25" y2="22" />
    <line x1="25" y1="22" x2="27.5" y2="16" />
  </g>
  <!-- Benchmark measurement target node at apex -->
  <rect class="apex-node" x="24.5" y="4" width="2" height="2" />
</svg>`;

writeFileSync(join(publicDir, "favicon.svg"), `${faviconSvg}\n`, "utf8");

// Convert a PNG buffer into an ICO format container
function pngToIco(pngBuffer, width = 32, height = 32) {
  const header = Buffer.alloc(6);
  header.writeUInt16LE(0, 0); // Reserved
  header.writeUInt16LE(1, 2); // 1 = ICO
  header.writeUInt16LE(1, 4); // 1 image

  const entry = Buffer.alloc(16);
  entry.writeUInt8(width === 256 ? 0 : width, 0);
  entry.writeUInt8(height === 256 ? 0 : height, 1);
  entry.writeUInt8(0, 2);
  entry.writeUInt8(0, 3);
  entry.writeUInt16LE(1, 4);
  entry.writeUInt16LE(32, 6);
  entry.writeUInt32LE(pngBuffer.length, 8);
  entry.writeUInt32LE(22, 12); // Offset = 6 + 16

  return Buffer.concat([header, entry, pngBuffer]);
}

// 2. Open Graph Card HTML (1200x630)
const ogHtml = `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<style>
  * {
    box-sizing: border-box;
    margin: 0;
    padding: 0;
    border-radius: 0;
  }
  body {
    width: 1200px;
    height: 630px;
    background: #141d32;
    color: #f8f9fc;
    font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
    padding: 32px;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    overflow: hidden;
  }
  .frame {
    width: 100%;
    height: 100%;
    border: 1px solid #2a3755;
    padding: 32px 36px;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    background: #141d32;
  }
  .header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    border-bottom: 1px solid #2a3755;
    padding-bottom: 16px;
  }
  .brand {
    display: flex;
    align-items: center;
    gap: 12px;
  }
  .logo-box {
    width: 32px;
    height: 32px;
  }
  .brand-title {
    font-size: 15px;
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: #f8f9fc;
  }
  .brand-sep {
    color: #536084;
    font-size: 14px;
  }
  .brand-subtitle {
    font-size: 13px;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: #aab9d8;
  }
  .badges {
    display: flex;
    align-items: center;
    gap: 12px;
  }
  .badge-passing {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 4px 10px;
    background: rgba(116, 207, 195, 0.12);
    border: 1px solid #74cfc3;
    color: #74cfc3;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.05em;
  }
  .badge-passing::before {
    content: "";
    display: inline-block;
    width: 6px;
    height: 6px;
    background: #74cfc3;
  }
  .platforms {
    font-size: 12px;
    color: #aab9d8;
    letter-spacing: 0.04em;
  }
  .hero {
    margin-top: 14px;
  }
  .title {
    font-size: 38px;
    font-weight: 700;
    letter-spacing: -0.03em;
    line-height: 1.15;
    color: #f8f9fc;
  }
  .lead {
    font-size: 17px;
    line-height: 1.4;
    color: #c7d2ed;
    margin-top: 8px;
    max-width: 950px;
  }
  .grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 24px;
    margin-top: 18px;
  }
  .card {
    border: 1px solid #2a3755;
    background: #17223b;
    padding: 16px 20px;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
  }
  .card-header {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    border-bottom: 1px solid #2a3755;
    padding-bottom: 8px;
    margin-bottom: 12px;
  }
  .card-title {
    font-size: 12px;
    font-weight: 700;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: #b3c5ff;
  }
  .card-meta {
    font-size: 11px;
    color: #aab9d8;
  }
  .cli-box {
    background: #121829;
    border: 1px solid #2a3755;
    padding: 8px 12px;
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    font-size: 12px;
    color: #f8f9fc;
    margin-bottom: 12px;
  }
  .cli-prompt {
    color: #74cfc3;
    user-select: none;
    margin-right: 6px;
  }
  .check-list {
    list-style: none;
    display: flex;
    flex-direction: column;
    gap: 6px;
    font-size: 12px;
  }
  .check-item {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }
  .check-item-name {
    color: #c7d2ed;
  }
  .check-item-status {
    color: #74cfc3;
    font-weight: 600;
    font-size: 11px;
  }
  .chart-bars {
    display: flex;
    flex-direction: column;
    gap: 10px;
  }
  .bar-row {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }
  .bar-info {
    display: flex;
    justify-content: space-between;
    font-size: 12px;
  }
  .bar-name {
    color: #f8f9fc;
    font-weight: 600;
  }
  .bar-val {
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    color: #c7d2ed;
    font-size: 12px;
  }
  .bar-track {
    width: 100%;
    height: 12px;
    background: #121829;
    border: 1px solid #2a3755;
    display: flex;
  }
  .bar-fill-fast {
    width: 14%;
    background: #74cfc3;
  }
  .bar-fill-mid {
    width: 36%;
    background: #91b4ff;
  }
  .bar-fill-base {
    width: 100%;
    background: #526d91;
  }
  .card-footer-note {
    font-size: 11px;
    color: #aab9d8;
    margin-top: 10px;
    border-top: 1px solid #2a3755;
    padding-top: 6px;
  }
  .footer {
    display: flex;
    justify-content: space-between;
    align-items: center;
    border-top: 1px solid #2a3755;
    padding-top: 14px;
    font-size: 12px;
    color: #aab9d8;
  }
  .footer-url {
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    color: #b3c5ff;
  }
</style>
</head>
<body>
<div class="frame">
  <div class="header">
    <div class="brand">
      <div class="logo-box">
        ${faviconSvg}
      </div>
      <div class="brand-title">Brightway Benchmarks</div>
      <div class="brand-sep">·</div>
      <div class="brand-subtitle">Evidence Workspace</div>
    </div>
    <div class="badges">
      <span class="badge-passing">Compatibility</span>
      <span class="platforms">Linux · macOS · Windows</span>
    </div>
  </div>

  <div class="hero">
    <h1 class="title">Continuous benchmarks for the Brightway LCA stack</h1>
    <p class="lead">Tested platform setups and noise-aware performance history on seeded synthetic matrices.</p>
  </div>

  <div class="grid">
    <div class="card">
      <div>
        <div class="card-header">
          <div class="card-title">Tested Setups</div>
          <div class="card-meta">uv · pip · conda · pixi</div>
        </div>
        <div class="cli-box">
          Choose a dated Brightway installation set
        </div>
        <ul class="check-list">
          <li class="check-item">
            <span class="check-item-name">Smoke calculations</span>
            <span class="check-item-status">View results</span>
          </li>
          <li class="check-item">
            <span class="check-item-name">Upstream package suites</span>
            <span class="check-item-status">View results</span>
          </li>
          <li class="check-item">
            <span class="check-item-name">Tested sparse solvers</span>
            <span class="check-item-status">UMFPACK · PyPardiso · SuperLU</span>
          </li>
        </ul>
      </div>
      <div class="card-footer-note">Dated install sets · Source-linked results</div>
    </div>

    <div class="card">
      <div>
        <div class="card-header">
          <div class="card-title">Solver Comparison</div>
          <div class="card-meta">ecoinvent size · 25k activities</div>
        </div>
        <div class="chart-bars">
          <div class="bar-row">
            <div class="bar-info">
              <span class="bar-name">UMFPACK (OpenBLAS)</span>
              <span class="bar-val">2.63 s</span>
            </div>
            <div class="bar-track">
              <div class="bar-fill-fast"></div>
            </div>
          </div>
          <div class="bar-row">
            <div class="bar-info">
              <span class="bar-name">PyPardiso</span>
              <span class="bar-val">10.0 s</span>
            </div>
            <div class="bar-track">
              <div class="bar-fill-mid"></div>
            </div>
          </div>
          <div class="bar-row">
            <div class="bar-info">
              <span class="bar-name">SuperLU (SciPy default)</span>
              <span class="bar-val">27.7 s · baseline</span>
            </div>
            <div class="bar-track">
              <div class="bar-fill-base"></div>
            </div>
          </div>
        </div>
      </div>
      <div class="card-footer-note">Beyond ±2% noise threshold · Apache Otava change points</div>
    </div>
  </div>

  <div class="footer">
    <div>Independent test suites · Seeded synthetic matrices · DOI 10.5281/zenodo.23727602</div>
    <div class="footer-url">simonvanlierde.com/brightway-benchmarks</div>
  </div>
</div>
</body>
</html>`;

const browser = await chromium.launch();

// 3. Render apple-touch-icon.png (180x180)
const iconPage = await browser.newPage({ viewport: { width: 180, height: 180 } });
await iconPage.emulateMedia({ colorScheme: "dark" });
await iconPage.setContent(`<!DOCTYPE html><html><body style="margin:0;overflow:hidden;background:#141d32;">
  ${faviconSvg.replace('width="32" height="32"', 'width="180" height="180"')}
</body></html>`);
const appleTouchBuf = await iconPage.screenshot({ type: "png" });
writeFileSync(join(publicDir, "apple-touch-icon.png"), appleTouchBuf);

// 4. Render 32x32 PNG for favicon.ico
const icoPage = await browser.newPage({ viewport: { width: 32, height: 32 } });
await icoPage.emulateMedia({ colorScheme: "dark" });
await icoPage.setContent(`<!DOCTYPE html><html><body style="margin:0;overflow:hidden;background:#141d32;">
  ${faviconSvg}
</body></html>`);
const icoPngBuf = await icoPage.screenshot({ type: "png" });
const icoBuf = pngToIco(icoPngBuf, 32, 32);
writeFileSync(join(publicDir, "favicon.ico"), icoBuf);

// 5. Render og.png (1200x630)
const ogPage = await browser.newPage({ viewport: { width: 1200, height: 630 }, deviceScaleFactor: 1 });
await ogPage.emulateMedia({ colorScheme: "dark" });
await ogPage.setContent(ogHtml);
const ogBuf = await ogPage.screenshot({ type: "png" });
writeFileSync(join(publicDir, "og.png"), ogBuf);

// 6. Render story-solver-choice.png (1200x630): the three one-score times of the solver story.
const storyBars = [
  ["UMFPACK, conda-forge on OpenBLAS", "2.63 s", 2.63, "#74cfc3"],
  ["PyPardiso", "10.0 s", 10.0, "#91b4ff"],
  ["SuperLU, SciPy's default", "27.7 s", 27.7, "#526d91"],
]
  .map(
    ([
      name,
      value,
      seconds,
      color,
    ]) => `<div class="row"><div class="info"><span>${name}</span><span class="mono">${value}</span></div>
    <div class="track"><div style="width:${(seconds / 27.7) * 100}%;background:${color}"></div></div></div>`,
  )
  .join("");
const storyHtml = `<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { width: 1200px; height: 630px; background: #141d32; color: #f8f9fc; padding: 56px 72px;
    font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; display: flex; flex-direction: column; }
  .kicker { font-size: 20px; color: #aab9d8; }
  h1 { font-size: 54px; line-height: 1.15; letter-spacing: -0.03em; margin: 16px 0 40px; max-width: 980px; }
  .row { margin-bottom: 22px; }
  .info { display: flex; justify-content: space-between; font-size: 24px; margin-bottom: 8px; }
  .mono { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; color: #c7d2ed; }
  .track { height: 22px; background: #121829; border: 1px solid #2a3755; }
  .track div { height: 100%; }
  .foot { margin-top: auto; display: flex; justify-content: space-between; font-size: 18px; color: #aab9d8; }
</style></head><body>
  <div class="kicker">Brightway benchmarks</div>
  <h1>The same LCA takes 2.6 s or 28 s, depending on one install choice</h1>
  ${storyBars}
  <div class="foot"><span>One score, ecoinvent-sized synthetic database, one thread</span><span class="mono">simonvanlierde.com/brightway-benchmarks</span></div>
</body></html>`;
const storyPage = await browser.newPage({ viewport: { width: 1200, height: 630 }, deviceScaleFactor: 1 });
await storyPage.emulateMedia({ colorScheme: "dark" });
await storyPage.setContent(storyHtml);
writeFileSync(join(publicDir, "story-solver-choice.png"), await storyPage.screenshot({ type: "png" }));

await browser.close();
console.log("Assets generated: favicon.svg, favicon.ico, apple-touch-icon.png, og.png, story-solver-choice.png");
