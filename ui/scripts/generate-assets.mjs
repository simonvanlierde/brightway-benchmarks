// Generates static branding assets for the Brightway Benchmarks viewer:
// - ui/public/favicon.svg (Scalable vector icon)
// - ui/public/favicon.ico (Standard 32x32 multi-platform favicon)
// - ui/public/apple-touch-icon.png (180x180 for iOS/mobile bookmarks)
// - ui/public/og.png (1200x630 Open Graph card for social sharing)
// - ui/public/story-solver-choice.png and story-home-heating.png (1200x630 cards for the stories)
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

// 2. Preview cards (1200x630), one layout for the site and each story: a poster whose headline and
// bars sit in the centred 630 px, so a square crop keeps both. Solver bars take the series colour the
// viewer's charts give that solver in the dark theme (ui/src/lib/story-series.ts: --s3, --s2, --s5).
const DARK = { umfpack: "#199e70", pypardiso: "#d95926", superlu: "#d55181", neutral: "#7488b3" };
function card({ title, caption, bars, titleSize = 62 }) {
  const longest = Math.max(...bars.map((b) => b.value));
  const rows = bars
    .map(
      (b) => `<div>
        <div class="bar-info"><span class="bar-name">${b.name}</span><span class="bar-val">${b.text}</span></div>
        <div class="bar-track"><div style="width:${(b.value / longest) * 100}%;background:${b.color}"></div></div>
      </div>`,
    )
    .join("");
  return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; border-radius: 0; }
  body {
    width: 1200px;
    height: 630px;
    background: #141d32;
    color: #f8f9fc;
    font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
    padding: 24px;
    overflow: hidden;
  }
  .frame {
    position: relative;
    padding-bottom: 20px;
    width: 100%;
    height: 100%;
    border: 1px solid #2a3755;
    display: flex;
    flex-direction: column;
    justify-content: center;
    align-items: center;
  }
  .logo-box { position: absolute; top: 28px; left: 32px; width: 48px; height: 48px; }
  .footer-url {
    position: absolute;
    bottom: 22px;
    right: 32px;
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    font-size: 20px;
    color: #aab9d8;
  }
  .center { width: 630px; }
  .title {
    font-size: ${titleSize}px;
    font-weight: 700;
    letter-spacing: -0.03em;
    line-height: 1.08;
    color: #f8f9fc;
    text-wrap: balance;
  }
  .chart { margin-top: 18px; display: flex; flex-direction: column; gap: 12px; }
  .chart-cap { margin-top: 22px; font-size: 26px; line-height: 1.2; color: #aab9d8; }
  .bar-info { display: flex; justify-content: space-between; align-items: baseline; font-size: 36px; line-height: 1.1; margin-bottom: 6px; }
  .bar-name { font-weight: 700; }
  .bar-val { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; color: #c7d2ed; font-size: 34px; }
  .bar-track { height: 18px; background: #121829; border: 1px solid #2a3755; }
  .bar-track div { height: 100%; }
</style>
</head>
<body>
<div class="frame">
  <div class="logo-box">${faviconSvg.replace('width="32" height="32"', 'width="48" height="48"')}</div>
  <div class="center">
    <h1 class="title">${title}</h1>
    <div class="chart-cap">${caption}</div>
    <div class="chart">${rows}</div>
  </div>
  <div class="footer-url">simonvanlierde.com/brightway-benchmarks</div>
</div>
</body>
</html>`;
}
const CARDS = {
  "og.png": card({
    title: "Continuous benchmarks for the Brightway LCA stack",
    caption: "One LCA score on an ecoinvent-sized database",
    bars: [
      { name: "UMFPACK", text: "2.63 s", value: 2.63, color: DARK.umfpack },
      { name: "PyPardiso", text: "10.0 s", value: 10.0, color: DARK.pypardiso },
      { name: "SuperLU", text: "27.7 s", value: 27.7, color: DARK.superlu },
    ],
  }),
  // The solver story's factorization times on real ecoinvent.
  "story-solver-choice.png": card({
    title: "Your solver choice can change a Brightway score's time by 5 times or more",
    titleSize: 46,
    caption: "Factorizing real ecoinvent 3.12, one thread",
    bars: [
      { name: "UMFPACK", text: "0.66 s", value: 0.66, color: DARK.umfpack },
      { name: "PyPardiso", text: "1.48 s", value: 1.48, color: DARK.pypardiso },
      { name: "SuperLU", text: "3.66 s", value: 3.66, color: DARK.superlu },
    ],
  }),
  // The findings page: one finding's release-to-release change, so neutral bars.
  "findings.png": card({
    title: "What the Brightway benchmarks found",
    titleSize: 54,
    caption: "bw2calc IterativeLCA with UMFPACK, one score",
    bars: [
      { name: "3.0.0", text: "45.0 s", value: 45.0, color: DARK.neutral },
      { name: "3.1.0", text: "9.04 s", value: 9.04, color: DARK.neutral },
    ],
  }),
  // The heating story's twenty-year climate scores: options, not solvers, so neutral bars.
  "story-home-heating.png": card({
    title: "Checking a home‑heating calculation", // a non-breaking hyphen
    titleSize: 54,
    caption: "Climate score over twenty years, t CO₂ eq",
    bars: [
      { name: "Heat pump", text: "23.2 t", value: 23.2, color: DARK.neutral },
      { name: "Gas boiler", text: "49.4 t", value: 49.4, color: DARK.neutral },
    ],
  }),
};

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

// 5. Render the preview cards
for (const [file, html] of Object.entries(CARDS)) {
  const page = await browser.newPage({ viewport: { width: 1200, height: 630 }, deviceScaleFactor: 1 });
  await page.emulateMedia({ colorScheme: "dark" });
  await page.setContent(html);
  writeFileSync(join(publicDir, file), await page.screenshot({ type: "png" }));
}

await browser.close();
console.log(`Assets generated: favicon.svg, favicon.ico, apple-touch-icon.png, ${Object.keys(CARDS).join(", ")}`);
