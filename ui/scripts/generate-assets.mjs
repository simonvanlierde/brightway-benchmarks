// Generates static branding assets for the Brightway Benchmarks viewer:
// - ui/public/favicon.svg (Scalable vector icon)
// - ui/public/favicon.ico (Standard 32x32 multi-platform favicon)
// - ui/public/apple-touch-icon.png (180x180 for iOS/mobile bookmarks)
// - ui/public/og.png (1200x630 Open Graph card for social sharing)
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "@playwright/test";

const __dirname = dirname(fileURLToPath(import.meta.url));
const publicDir = join(__dirname, "../public");
mkdirSync(publicDir, { recursive: true });

// Design tokens from DESIGN.md
const colors = {
  darkPage: "#141d32",
  darkInk: "#f8f9fc",
  darkInk2: "#c7d2ed",
  darkMuted: "#aab9d8",
  darkGrid: "#2a3755",
  darkAxis: "#6b7fa9",
  darkLine: "#3d4d70",
  darkAccent: "#b3c5ff",
  darkBetter: "#74cfc3",
};

// 1. Scalable SVG Favicon
const faviconSvg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32" width="32" height="32">
  <title>Brightway Benchmarks</title>
  <rect width="32" height="32" fill="${colors.darkPage}" />
  <rect x="0.5" y="0.5" width="31" height="31" fill="none" stroke="${colors.darkGrid}" stroke-width="1" />
  <!-- Baseline rule -->
  <line x1="5" y1="25" x2="27" y2="25" stroke="${colors.darkLine}" stroke-width="1.5" />
  <!-- Benchmark columns: SuperLU (baseline), PyPardiso (intermediate), UMFPACK (optimal) -->
  <rect x="6" y="18" width="5" height="7" fill="${colors.darkAxis}" />
  <rect x="13.5" y="12" width="5" height="13" fill="${colors.darkAccent}" />
  <rect x="21" y="6" width="5" height="19" fill="${colors.darkBetter}" />
  <!-- Benchmark dot on top of the fastest column -->
  <rect x="22.5" y="7.5" width="2" height="2" fill="${colors.darkInk}" />
</svg>`;

writeFileSync(join(publicDir, "favicon.svg"), faviconSvg, "utf8");

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
      <span class="badge-passing">Passing</span>
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
          <span class="cli-prompt">$</span>uv add "bw2data&gt;=4.8" "bw2calc&gt;=3.1.0"
        </div>
        <ul class="check-list">
          <li class="check-item">
            <span class="check-item-name">Smoke calculations · Python 3.12</span>
            <span class="check-item-status">Passing</span>
          </li>
          <li class="check-item">
            <span class="check-item-name">Upstream package suites</span>
            <span class="check-item-status">187 passed</span>
          </li>
          <li class="check-item">
            <span class="check-item-name">Tested sparse solvers</span>
            <span class="check-item-status">UMFPACK · PyPardiso · SuperLU</span>
          </li>
        </ul>
      </div>
      <div class="card-footer-note">Dated install sets · Never invented recommendations</div>
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
              <span class="bar-val">2.63 s · 10.5× faster</span>
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
    <div class="footer-url">simonvanlierde.github.io/brightway-benchmarks</div>
  </div>
</div>
</body>
</html>`;

const browser = await chromium.launch();

// 3. Render apple-touch-icon.png (180x180)
const iconPage = await browser.newPage({ viewport: { width: 180, height: 180 } });
await iconPage.setContent(`<!DOCTYPE html><html><body style="margin:0;overflow:hidden;background:#141d32;">
  ${faviconSvg.replace('width="32" height="32"', 'width="180" height="180"')}
</body></html>`);
const appleTouchBuf = await iconPage.screenshot({ type: "png" });
writeFileSync(join(publicDir, "apple-touch-icon.png"), appleTouchBuf);

// 4. Render 32x32 PNG for favicon.ico
const icoPage = await browser.newPage({ viewport: { width: 32, height: 32 } });
await icoPage.setContent(`<!DOCTYPE html><html><body style="margin:0;overflow:hidden;background:#141d32;">
  ${faviconSvg}
</body></html>`);
const icoPngBuf = await icoPage.screenshot({ type: "png" });
const icoBuf = pngToIco(icoPngBuf, 32, 32);
writeFileSync(join(publicDir, "favicon.ico"), icoBuf);

// 5. Render og.png (1200x630)
const ogPage = await browser.newPage({ viewport: { width: 1200, height: 630 }, deviceScaleFactor: 1 });
await ogPage.setContent(ogHtml);
const ogBuf = await ogPage.screenshot({ type: "png" });
writeFileSync(join(publicDir, "og.png"), ogBuf);

await browser.close();
console.log("Assets generated: favicon.svg, favicon.ico, apple-touch-icon.png, og.png");
