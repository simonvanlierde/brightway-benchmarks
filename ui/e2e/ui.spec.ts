import { readFile } from "node:fs/promises";
import AxeBuilder from "@axe-core/playwright";
import { expect, type Page, test } from "@playwright/test";
import type { Guidance } from "../src/lib/contract";
import { latestChanges, writeView } from "../src/lib/history";

// Screenshots go to SHOTS when it is set, so a reviewer can look at them; CI keeps them as an artifact.
const shots = process.env.SHOTS ?? "test-results/shots";
const IMPORT = "?bench=bw2calc-bench-import-timeraw-import-bw2calc-c078f5d2c0be";
const SCORES = "?bench=bw2calc-bench-lca-multiscores-time-scores-4f172f3e24a0&p=ecoinvent&p=3&p=MultiLCA";
const MONTE_CARLO =
  "?bench=bw2calc-bench-lca-montecarlo-time-iterations-00a0cd27d056&p=ecoinvent&p=10&p=JacobiGMRESLCA";

async function chart(page: Page, url: string) {
  await page.goto(url);
  await page.locator(".chart svg").waitFor();
}

test.describe("looks", () => {
  for (const [name, scheme, width, height] of [
    ["light", "light", 1440, 1000],
    ["dark", "dark", 1440, 1000],
    ["phone", "light", 390, 844],
    ["phone-dark", "dark", 390, 844],
  ] as const) {
    test(name, async ({ page }) => {
      await page.setViewportSize({ width, height });
      await page.emulateMedia({ colorScheme: scheme });
      await chart(page, SCORES);
      await page.mouse.move(0, 0);
      await page.screenshot({ path: `${shots}/bench-${name}-viewport.png` });
      await page.locator(".chart").focus();
      await page.keyboard.press("End");
      await page.getByText(/^Data table/).click();
      await page.evaluate(() => scrollTo(0, 0));
      await page.screenshot({ path: `${shots}/bench-${name}.png`, fullPage: true });
      // Nothing wider than the screen: the tables scroll inside their own box.
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      await page.goto("?page=changes");
      await expect(page.getByRole("heading", { name: "What changed in the latest releases" })).toBeVisible();
      await page.screenshot({ path: `${shots}/start-${name}.png`, fullPage: true });
      await page.screenshot({ path: `${shots}/start-${name}-viewport.png` });
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    });
  }
});

test("the view lives in the URL, and back goes back", async ({ page }) => {
  await chart(page, SCORES);
  await page.getByLabel("Scoring", { exact: true }).selectOption("adjoint");
  await expect(page).toHaveURL(/p=adjoint/);
  await page.reload();
  await expect(page.getByLabel("Scoring", { exact: true })).toHaveValue("adjoint");
  await expect(page.getByLabel("Functional units", { exact: true })).toHaveValue("3");
  await page.getByRole("link", { name: "Import bw2calc" }).first().click();
  await expect(page.getByRole("main").getByRole("heading", { level: 2 })).toHaveText("Import bw2calc");
  await page.goBack();
  await expect(page.getByLabel("Scoring", { exact: true })).toHaveValue("adjoint");
});

test("the start page links each change to its chart", async ({ page }) => {
  await page.goto("?page=changes");
  const first = page.locator("tbody tr").first().getByRole("link");
  const name = await first.textContent();
  await first.click();
  await expect(page.getByRole("main").getByRole("heading", { level: 2 })).toHaveText(name ?? "");
  await expect(page.locator(".chart svg")).toBeVisible();
});

test("the keyboard reads each release, and the pointer shows the same tip", async ({ page }) => {
  await chart(page, IMPORT);
  const chartBox = page.locator(".chart");
  await chartBox.focus();
  await page.keyboard.press("Home");
  const said = page.locator("p[aria-live]").last();
  await expect(said).toContainText("2.0 ·");
  await page.keyboard.press("ArrowRight");
  await expect(said).toContainText("2.0.1 ·");
  await page.keyboard.press("End");
  await expect(said).toContainText("SuperLU:");
  await expect(page.locator(".chart svg [data-mark='tip']").filter({ hasText: "SuperLU:" })).toHaveCount(1);
  await page.keyboard.press("Escape");
  await expect(said).toHaveText("");
  const box = await page.locator(".chart svg").boundingBox();
  if (!box) throw new Error("no chart");
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2, { steps: 4 });
  await expect(page.locator(".chart svg [data-mark='tip']").filter({ hasText: "SuperLU:" })).toHaveCount(1);
  await expect(page.locator(".chart svg g[aria-label]")).toHaveCount(0);
});

test("change points and release changes are marked and listed", async ({ page }) => {
  await chart(page, IMPORT);
  await expect(page.locator("[data-mark='rule']")).not.toHaveCount(0); // Otava's level shifts
  const changes = page.getByRole("table", { name: "Changes" });
  await expect(changes.getByText("level shift in the series").first()).toBeVisible();
  await expect(changes.getByText(/beyond ±[\d.]+% noise/).first()).toBeVisible();
});

test("every chart has a table behind it", async ({ page }) => {
  await chart(page, SCORES);
  await page.getByText(/^Data table/).click();
  const table = page.getByRole("region", { name: "Data table" }).getByRole("table");
  await expect(table.locator("thead th")).toHaveCount(2 + 5); // release, date, five environments
  await expect(table.locator("tbody tr")).not.toHaveCount(0);
});

test("the chart downloads as a standalone SVG", async ({ page }) => {
  await chart(page, IMPORT);
  const [download] = await Promise.all([
    page.waitForEvent("download"),
    page.getByRole("button", { name: "Download SVG" }).click(),
  ]);
  expect(download.suggestedFilename()).toBe("bench_import.timeraw_import_bw2calc.svg");
  const text = await (await download.createReadStream()).toArray();
  const svg = Buffer.concat(text).toString();
  expect(svg).toContain('xmlns="http://www.w3.org/2000/svg"');
  expect(svg).not.toContain("var(--");
});

test("a missing data folder says what went wrong", async ({ page }) => {
  await page.route("**/data/index.json", (route) => route.fulfill({ status: 404, body: "" }));
  await page.goto("?page=changes");
  await expect(page.getByRole("alert")).toContainText(
    "The results could not load. Reload the page, or try again later.",
  );
  await expect(page.getByText("HTTP 404")).toBeHidden();
  await page.getByText("Technical details").click();
  await expect(page.getByRole("alert")).toContainText("HTTP 404");
  await expect(page.getByRole("alert")).toContainText("Check that index.json is in the data folder");
});

test("a newer format says so, in the main column", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.route("**/data/index.json", async (route) => {
    const index = await (await route.fetch()).json();
    await route.fulfill({ json: { ...index, format_version: 99 } });
  });
  await page.goto("?page=changes");
  await expect(page.getByRole("alert")).toContainText("format_version 99");
  await expect(page.getByRole("alert")).toContainText("newer or older format");
  await expect(page.getByRole("main").getByRole("alert")).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test("one missing report leaves the rest of the chart", async ({ page }) => {
  let first = true;
  await page.route("**/data/reports/bw2calc-*/**", (route) => {
    if (!first) return route.continue();
    first = false;
    return route.fulfill({ status: 404, body: "" });
  });
  await chart(page, IMPORT);
  await expect(page.locator("main").getByRole("status")).toContainText("1 of 15 reports did not load");
});

test("data without changes says they were not exported", async ({ page }) => {
  await page.route("**/data/index.json", async (route) => {
    const { changes: _, ...index } = await (await route.fetch()).json();
    await route.fulfill({ json: index });
  });
  await page.goto("?page=changes");
  await expect(page.getByText("Changes were not exported")).toBeVisible();
});

test("a skip link leads to the results, and a one-value axis is plain text", async ({ page }) => {
  await chart(page, SCORES);
  await page.keyboard.press("Tab");
  await expect(page.getByRole("link", { name: "Skip to the results" })).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.locator("#main")).toBeFocused();
  await expect(page.getByLabel("Synthetic database", { exact: true })).toHaveCount(0);
  await expect(page.locator(".fixed")).toHaveText("ecoinvent");
  await expect(page.locator(".fixed a")).toHaveCount(0);
  await expect(page.getByLabel("Scoring", { exact: true })).toBeVisible();
});

for (const [scheme, width] of [
  ["light", 1280],
  ["dark", 1280],
  ["light", 375],
  ["dark", 375],
] as const) {
  for (const [where, url] of [
    ["start", "?page=changes"],
    ["benchmark", SCORES],
  ] as const) {
    test(`axe: no WCAG 2.2 AA violations, ${where}, ${scheme}, ${width} px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 800 });
      await page.emulateMedia({ colorScheme: scheme });
      if (where === "start") {
        await page.goto(url);
        await page.locator("tbody tr").first().waitFor();
      } else {
        await chart(page, url);
        await page.getByText(/^Data table/).click();
        await page.locator(".chart").focus();
        await page.keyboard.press("End");
      }
      const result = await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa", "best-practice"])
        .analyze();
      expect(result.violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target).join(" | ")}`)).toEqual([]);
    });
  }
}

test("overview filters scope their counts and survive a shared URL", async ({ page }) => {
  await page.goto("?page=changes");
  await expect(page.getByRole("button", { name: /^Worse/ })).toBeVisible();
  await page.getByLabel("Package", { exact: true }).selectOption({ label: "bw_processing" });
  await expect(page.getByRole("button", { name: /^All changes/ })).toHaveText("All changes 3");
  await expect(page.getByRole("button", { name: /^Worse/ })).toHaveText("Worse 0");
  await expect(page.getByRole("button", { name: /^Better/ })).toHaveText("Better 3");
  await page.getByRole("button", { name: /^Worse/ }).click();
  await expect(page.getByText("No changes match these filters")).toBeVisible();
  await expect(page).toHaveURL(/group=bw-processing/);
  await expect(page).toHaveURL(/direction=worse/);
  await page.reload();
  await expect(page.getByRole("button", { name: /^Worse/ })).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByLabel("Package", { exact: true })).toHaveValue("bw-processing-dfb1fd2e3103");
  await page.getByRole("button", { name: /^Better/ }).click();
  // Three improvements in two benchmarks: one row each, the cases inside.
  await expect(page.locator(".gains-table tbody tr")).toHaveCount(2);
  await expect(page.locator(".gains-table summary")).toHaveText(["2 cases", "1 case"]);
  // The Better count is cases, not rows, so the caption reconciles the two.
  await expect(page.locator(".gains-table caption")).toContainText("2 benchmarks with 3 improved cases");
  await expect(page.locator(".gains-table tbody tr").first()).toContainText("bw_processing");
  await page.getByRole("button", { name: "Clear filters" }).click();
  await expect(page.getByLabel("Package", { exact: true })).toHaveValue("");
  await expect(page.getByRole("button", { name: /^All changes/ })).toHaveAttribute("aria-pressed", "true");
});

test("release changes list regressions before grouped improvements", async ({ page }) => {
  await page.goto("?page=changes");
  const changes = page.getByRole("region", { name: "What changed in the latest releases" });
  await expect(changes.getByRole("heading", { level: 3 })).toHaveText(["Regressions", "Improvements"]);
  const better = Number((await page.getByRole("button", { name: /^Better/ }).textContent())?.match(/\d+/)?.[0]);
  const cases = await page.locator(".gains-table summary").allTextContents();
  expect(cases.reduce((sum, text) => sum + Number.parseInt(text, 10), 0)).toBe(better);
});

test("the solver comparison says which platform it was measured on", async ({ page }) => {
  await page.goto("?platform=linux");
  await expect(page.getByRole("heading", { name: /measured on one Linux machine/ })).toBeVisible();
  await expect(page.getByText(/No Linux machine was timed/)).toHaveCount(0);
  await page.goto("?platform=windows");
  await expect(page.getByText("No Windows machine was timed, so these values may not hold there.")).toBeVisible();
});

test("a legend button brings one environment forward and keeps focus", async ({ page }) => {
  await chart(page, SCORES);
  const key = page.locator(".legend-host button").first();
  await key.focus();
  await page.keyboard.press("Enter");
  await expect(page.locator(".legend-host button").first()).toHaveAttribute("aria-pressed", "true");
  await expect(page.locator(".legend-host button").first()).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.locator(".legend-host button").first()).toHaveAttribute("aria-pressed", "false");
});

test("Benchmarks opens on the findings, and each finding opens its chart", async ({ page }) => {
  const index = JSON.parse(await readFile(new URL("../test/fixtures/real/index.json", import.meta.url), "utf8"));
  await page.goto("?page=explorer");
  const findings = page.getByRole("region", { name: "What the benchmarks show" });
  await expect(findings.getByRole("heading", { level: 3 })).toHaveText(
    index.findings.map((f: { title: string }) => f.title),
  );
  await expect(page.getByRole("heading", { name: "What changed in the latest releases" })).toBeVisible();
  await findings
    .getByRole("link", { name: /JacobiGMRESLCA/ })
    .first()
    .click();
  await expect(page.getByLabel("Calculation class", { exact: true })).toHaveValue("JacobiGMRESLCA");
  await expect(page.locator(".chart svg")).toBeVisible();
});

test("Setup leaves out the finding its solver chart already shows", async ({ page }) => {
  await page.goto("./");
  const findings = page.getByRole("region", { name: "What the benchmarks show" });
  await expect(findings.getByRole("heading", { level: 3 }).first()).toBeVisible();
  await expect(findings.getByRole("heading", { name: "The solver sets the time for one score" })).toHaveCount(0);
  await expect(
    findings.getByRole("link", { name: "Write-up on bw2calc 3.0.0 slowed IterativeLCA, and 3.1.0 fixed it" }),
  ).toBeVisible();
});

test("the explorer explains the benchmark and links the chosen values", async ({ page }) => {
  await chart(page, MONTE_CARLO);
  await expect(page.locator(".bench-about")).not.toBeEmpty();
  const cls = page.getByLabel("Calculation class", { exact: true });
  const note = page.locator(".field").filter({ has: cls }).locator(".field-note");
  await expect(note).toContainText("JacobiGMRESLCA: Solves by GMRES");
  await expect(note.getByRole("link", { name: "JacobiGMRESLCA" })).toHaveAttribute("href", /docs\.brightway\.dev/);
  await cls.selectOption("LCA");
  await expect(note).toContainText("LCA: Solves directly");
  await expect(page.locator(".benchmark-id a")).toHaveAttribute("href", /\/blob\/main\/benchmarks\/.+\.py$/);
  await expect(page.locator(".env-links a").first()).toHaveAttribute("href", /^https:/);
});

test("clearing a shared package filter stays on release changes", async ({ page }) => {
  // A link from before the page parameter: the filters alone chose the changes page.
  await page.goto("?group=bw-processing-dfb1fd2e3103");
  const heading = page.getByRole("heading", { name: "What changed in the latest releases" });
  await expect(heading).toBeVisible();
  await expect(page.locator("main").getByRole("status")).toHaveText("3 of 3 changes shown");
  await page.getByLabel("Package", { exact: true }).selectOption({ label: "All packages" });
  await expect(heading).toBeVisible();
  await expect(page).toHaveURL(/page=explorer/);
  await page.reload();
  await expect(heading).toBeVisible();
});

test("chosen filters stay visible in high contrast mode", async ({ page }) => {
  await page.emulateMedia({ forcedColors: "active" });
  await page.goto("?page=changes&direction=worse");
  const outline = (name: RegExp) =>
    page.getByRole("button", { name }).evaluate((b) => getComputedStyle(b).outlineStyle);
  expect(await outline(/^Worse/)).toBe("solid");
  expect(await outline(/^Better/)).toBe("none");
});

test("a link to another page moves keyboard focus to that page", async ({ page }) => {
  await page.goto("./");
  await page.getByRole("link", { name: "Open all release changes" }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("heading", { name: "What changed in the latest releases" })).toBeVisible();
  await expect(page.locator("#main")).toBeFocused();
});

test("the masthead search filters the catalogue and opens the first match", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto("./");
  const search = page.getByRole("searchbox", { name: "Find a benchmark" });
  await search.fill("MultiLCA");
  await expect(page).toHaveURL(/page=explorer/);
  await expect(page.getByRole("navigation", { name: "Benchmarks" }).locator("li a")).toHaveCount(2);
  await search.fill("timeraw_import_bw2calc");
  await expect(page.getByRole("navigation", { name: "Benchmarks" }).locator("li a")).toHaveCount(2);
  await search.fill("missing-case");
  await expect(page.getByText("No benchmarks match")).toBeVisible();
  await search.fill("timeraw_import_bw2calc");
  await search.press("Enter");
  await expect(page.locator(".benchmark-id")).toContainText("bench_import.timeraw_import_bw2calc");
});

for (const width of [390, 1440]) {
  test(`search keeps results visible and typing focused at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.goto("./");
    // A phone keeps the search behind an icon.
    if (width < 600) await page.getByRole("button", { name: "Show the benchmark search" }).click();
    const search = page.getByRole("searchbox", { name: "Find a benchmark" });
    await search.focus();
    await search.pressSequentially("import");
    await expect(search).toBeFocused();
    await expect(search).toHaveValue("import");
    const catalogue = page.getByRole("navigation", { name: "Benchmarks" });
    await expect(catalogue.locator("li a").first()).toBeVisible();
    await search.fill("missing-case");
    await expect(catalogue.getByText("No benchmarks match")).toBeVisible();
  });
}

// Two tiers: evidence a reader acts on is 14px or more; 12px is for meta (dates, build ids, captions) and the floor.
test("benchmark explanations keep the design's text tiers", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await chart(page, SCORES);
  const size = (selector: string) =>
    page
      .locator(selector)
      .evaluateAll((nodes) => nodes.map((node) => Number.parseFloat(getComputedStyle(node).fontSize)));
  const evidence = [
    ...(await size(".field-note")),
    ...(await size(".reading-guide")),
    ...(await size(".env-notes dd")),
  ];
  expect(evidence.length).toBeGreaterThan(0);
  expect(Math.min(...evidence)).toBeGreaterThanOrEqual(14);
  const meta = await size(".benchmark-id");
  expect(meta.length).toBeGreaterThan(0);
  expect(Math.min(...meta)).toBeGreaterThanOrEqual(12);
});

test("an unknown benchmark link names the problem", async ({ page }) => {
  await page.goto("?bench=missing-case");
  await expect(page.getByText("This benchmark is not in the current data")).toHaveRole("status");
});

test("a change opens the same machine's history", async ({ page }) => {
  await page.route("**/data/index.json", async (route) => {
    const index = await (await route.fetch()).json();
    const row = latestChanges(index)[0];
    if (!row) throw new Error("fixture has no latest change");
    const machine = { id: "comparison-machine", name: "Comparison machine" };
    index.machines.push(machine);
    index.reports.push(...index.reports.map((report: { machine: string }) => ({ ...report, machine: machine.id })));
    index.changes = [{ ...row.change, machine: machine.id }];
    await route.fulfill({ json: index });
  });
  await page.goto("?page=changes");
  const row = page.locator(".latest-table tbody tr").first();
  const rowText = await row.textContent();
  await row.getByRole("link").click();
  await expect(page).toHaveURL(/machine=comparison-machine/);
  await expect(page.getByLabel("Machine", { exact: true })).toHaveValue("comparison-machine");
  expect(rowText).toContain("Comparison machine");
  await expect(page.locator(".chart svg")).toBeVisible();
});

test("the masthead has a Setup and a Benchmarks page", async ({ page }) => {
  await page.goto("./");
  const main = page.getByRole("navigation", { name: "Main", exact: true });
  await expect(main.getByRole("link")).toHaveText(["Setup", "Benchmarks"]);
  await expect(main.getByRole("link", { name: "Setup", exact: true })).toHaveAttribute("aria-current", "page");
  await expect(page.getByRole("navigation", { name: "Benchmarks", exact: true })).toHaveCount(0);
  await main.getByRole("link", { name: "Benchmarks", exact: true }).click();
  await expect(page).toHaveURL(/page=explorer/);
  await expect(page).toHaveTitle(/^Benchmarks ·/);
  await page.goBack();
  await expect(main.getByRole("link", { name: "Setup", exact: true })).toHaveAttribute("aria-current", "page");
});

test("old links open the page that took their place", async ({ page }) => {
  await page.goto("?page=explorer&group=bw2calc&bench=bench_lca.MultiScores.time_scores");
  await expect(page.locator(".benchmark-id")).toContainText("bench_lca.MultiScores.time_scores");
  await expect(page.locator(".bench-meta")).toContainText("bw2calc ·");
  await page.goto("?page=changes");
  await expect(page.getByRole("heading", { name: "What changed in the latest releases" })).toBeVisible();
  await page.goto("?page=compatibility");
  await expect(page).toHaveTitle(/^Setup ·/);
  await expect(page.locator("#all-checks")).toBeInViewport();
});

test("each page's main content fits a 1440 by 900 laptop screen", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  const fits = async (selector: string) => {
    const box = await page.locator(selector).first().boundingBox();
    expect(box && box.y + box.height, selector).toBeLessThanOrEqual(900);
  };
  await page.goto("?platform=linux");
  await page.locator(".install-set > .install-command").waitFor();
  await fits(".install-set > .install-command");
  await page.goto("?page=explorer");
  await page.locator(".findings").waitFor();
  await fits(".findings");
  await chart(page, SCORES);
  await fits(".chart svg");
});

test.describe("guidance looks", () => {
  for (const [name, scheme, width, height] of [
    ["light", "light", 1440, 1000],
    ["dark", "dark", 1440, 1000],
    ["phone", "light", 390, 844],
    ["phone-dark", "dark", 390, 844],
  ] as const) {
    test(name, async ({ page }) => {
      await page.setViewportSize({ width, height });
      await page.emulateMedia({ colorScheme: scheme });
      await page.goto("?page=home&platform=linux");
      await page.getByRole("link", { name: "requirements.txt", exact: true }).waitFor();
      await page.screenshot({ path: `${shots}/home-${name}-viewport.png` });
      await page.screenshot({ path: `${shots}/home-${name}.png`, fullPage: true });
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    });
  }
});

const guidanceFixture = async (): Promise<Guidance> =>
  JSON.parse(await readFile(new URL("../test/fixtures/real/guidance.json", import.meta.url), "utf8"));

test("check qualifications precede the install command", async ({ page }) => {
  await page.goto("?platform=linux");
  const results = page.getByRole("list", { name: "Check results on Linux" });
  await expect(results.getByRole("listitem")).toHaveText([
    "Smoke calculations · Latest releases · Python 3.12 Passed",
    "Upstream test suites · Python 3.12 Failed",
  ]);
  const after = await results.evaluate(
    (el) =>
      !!(
        el.compareDocumentPosition(document.querySelector(".install-set > .install-command") as Node) &
        Node.DOCUMENT_POSITION_FOLLOWING
      ),
  );
  expect(after).toBe(true);
});

test("the install command copies", async ({ page, context, browserName }) => {
  test.skip(browserName !== "chromium", "clipboard permissions are Chromium's");
  await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  await page.goto("?platform=windows");
  await page.locator(".install-set > .install-command").getByRole("button", { name: "Copy" }).click();
  await expect(page.locator(".install-meta [role=status]")).toHaveText("Copied command");
  const text = await page.evaluate(() => navigator.clipboard.readText());
  await expect(page.locator(".install-set > .install-command pre")).toHaveText(text);
  await page.getByRole("button", { name: "Copy latest" }).click();
  const latest = await page.evaluate(() => navigator.clipboard.readText());
  expect(latest).toContain("/compat/latest-3.12-windows-latest/requirements.txt");
  expect(latest).not.toContain("2026-");
});

test("environments on a two-release chart sit apart", async ({ page }) => {
  const index = JSON.parse(await readFile(new URL("../test/fixtures/real/index.json", import.meta.url), "utf8"));
  const worst = latestChanges(index).find((r) => r.way === "worse");
  if (!worst) throw new Error("fixture has no regression");
  await page.goto(writeView({ bench: worst.bench.id, params: worst.params }));
  const dots = page.locator('.chart [data-mark="dot"]');
  await expect(dots.first()).toBeAttached();
  const at = await dots.evaluateAll((gs) => gs.map((g) => g.getAttribute("transform") ?? ""));
  expect(new Set(at).size).toBeGreaterThan(1);
});

test("commits that are not releases are named under the chart", async ({ page }) => {
  await page.goto("?bench=bw2data-bench-write-databasewrite-time-write-e538eba4ffdf");
  await expect(page.locator(".chart svg")).toBeVisible();
  await expect(page.getByText(/not a\s+release and (is|are) drawn faint/)).toBeVisible();
});

test("platform setups keep their pins, install command and URL together", async ({ page }) => {
  const data = await guidanceFixture();
  await page.goto("?page=home&platform=linux");
  const windows = data.platforms.find((p) => p.id === "windows");
  const check = data.checks.find((c) => c.id === windows?.defaultCheck);
  const uv = check?.lastPassed?.installs.find((i) => i.manager === "uv");
  if (!windows || !check?.lastPassed || !uv) throw new Error("fixture lacks a Windows setup");
  await page.getByRole("combobox", { name: "Operating system" }).selectOption("windows");
  await expect(page).toHaveURL(/platform=windows/);
  await expect(page.locator(".install-set > .install-command pre")).toHaveText(uv.command);
  await expect(page.getByRole("link", { name: "requirements.txt", exact: true })).toHaveAttribute(
    "href",
    check.lastPassed.files.find((f) => f.label === "requirements.txt")?.url ?? "",
  );
  await page.reload();
  await expect(page.getByRole("combobox", { name: "Operating system" })).toHaveValue("windows");
  await page.goBack();
  await expect(page.getByRole("combobox", { name: "Operating system" })).toHaveValue("linux");
});

test("a check chosen in the grid shows its set and survives shared URLs and back", async ({ page }) => {
  await page.goto("?platform=linux");
  const cell = page.getByRole("link", { name: "Linux · Python 3.14, Pre-releases: Passed" });
  await cell.click();
  await expect(page).toHaveURL(/check=pre-3\.14-/);
  await expect(page.locator("#install-heading")).toBeFocused();
  await expect(page.locator(".install-set > .install-command pre")).toContainText("pre-3.14-ubuntu-latest");
  await expect(cell).toHaveAttribute("aria-current", "true");
  const link = page.url();
  await page.reload();
  await expect(page.locator(".install-set > .install-command pre")).toContainText("pre-3.14-ubuntu-latest");
  await page.getByRole("combobox", { name: "Operating system" }).selectOption("macos");
  await expect(page.locator(".install-set > .install-command pre")).toContainText("macos-latest");
  await page.goBack();
  await expect(page).toHaveURL(link);
  await expect(page).toHaveTitle(/^Setup ·/);
});

test("a failed current check keeps its older passing files clearly dated", async ({ page }) => {
  const data = await guidanceFixture();
  const current = data.checks.find((c) => c.id === data.platforms.find((p) => p.id === "linux")?.defaultCheck);
  if (!current?.lastPassed) throw new Error("fixture lacks Linux saved set");
  current.status = "failure";
  current.lastPassed.date = "2026-10-30";
  await page.route("**/data/guidance.json", (route) => route.fulfill({ json: data }));
  await page.goto("?page=home&platform=linux");
  await expect(page.getByRole("list", { name: "Check results on Linux" }).getByRole("listitem").first()).toHaveText(
    "Smoke calculations · Latest releases · Python 3.12 Failed",
  );
  await expect(page.locator(".saved-warning")).toHaveText(
    "The latest run of Latest releases did not pass; this is the set that passed on Oct 30, 2026.",
  );
  await expect(page.getByRole("link", { name: "requirements.txt", exact: true })).toBeVisible();
});

for (const [label, status, json] of [
  ["absent", 404, {}],
  ["invalid", 200, { format_version: 99 }],
  ["failed", 500, {}],
] as const) {
  test(`${label} guidance leaves benchmark navigation usable`, async ({ page }) => {
    await page.route("**/data/guidance.json", (route) => route.fulfill({ status, json }));
    await page.goto("./");
    await expect(page.getByRole("heading", { name: "Explore the available evidence", exact: true })).toBeVisible();
    await expect(page.getByRole("link", { name: "requirements.txt", exact: true })).toHaveCount(0);
    if (status !== 404)
      await expect(page.locator("main").getByRole("status")).toContainText("Setup guidance could not be loaded");
    await page
      .getByRole("navigation", { name: "Main", exact: true })
      .getByRole("link", { name: "Benchmarks", exact: true })
      .click();
    await expect(page.getByRole("heading", { name: "What changed in the latest releases" })).toBeVisible();
  });
}

test("home includes both change directions and solver links retain the measured view", async ({ page }) => {
  const data = await guidanceFixture();
  await page.goto("?page=home&platform=linux");
  await expect(page.locator(".brief-change .worse")).toBeVisible();
  await expect(page.locator(".brief-change .better")).toBeVisible();
  const index = JSON.parse(await readFile(new URL("../test/fixtures/real/index.json", import.meta.url), "utf8"));
  const changes = latestChanges(index);
  for (const [at, way] of ["worse", "better"].entries()) {
    const row = changes.find((c) => c.way === way);
    if (!row) throw new Error(`fixture lacks a ${way} change`);
    const href = await page.locator(".brief-change h3 a").nth(at).getAttribute("href");
    const linked = new URL(href ?? "", "http://example.test").searchParams;
    expect(linked.get("machine")).toBe(row.change.machine);
    expect(linked.get("bench")).toBe(row.bench.id);
  }
  const solver = data.solverComparison?.rows[0];
  if (!solver) throw new Error("fixture lacks solver comparison");
  const expected = new URL(solver.href, "http://example.test").searchParams;
  await page.getByRole("link", { name: solver.label, exact: true }).click();
  const got = new URL(page.url()).searchParams;
  for (const key of ["bench", "machine", "measure"]) expect(got.get(key)).toBe(expected.get(key));
  expect(got.getAll("p")).toEqual(expected.getAll("p"));
  await expect(page.locator(".chart svg")).toBeVisible();
});

test("on a phone, a check chosen in the list brings its install command into view", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("?platform=linux");
  await page.getByRole("link", { name: "Linux · Latest releases Python 3.13 Passed" }).click();
  await expect(page.locator("#install-heading")).toBeFocused();
  await expect(page.locator(".install-set > .install-command")).toBeInViewport();
});

for (const scheme of ["light", "dark"] as const) {
  for (const width of [1440, 390]) {
    for (const route of ["home"]) {
      test(`guidance axe: ${route}, ${scheme}, ${width}px`, async ({ page }) => {
        await page.setViewportSize({ width, height: 900 });
        await page.emulateMedia({ colorScheme: scheme });
        await page.goto(`?page=${route}&platform=linux`);
        await page.getByRole("link", { name: "requirements.txt", exact: true }).waitFor();
        const result = await new AxeBuilder({ page })
          .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa", "best-practice"])
          .analyze();
        expect(result.violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target).join(" | ")}`)).toEqual([]);
      });
    }
  }
}

test("each package manager has its own command, and the choice is remembered", async ({ page }) => {
  await page.goto("?platform=linux");
  const command = page.locator(".install-set > .install-command pre");
  await expect(command).toContainText("uv add brightway25 bw_graph_tools bw_timex -c https://");
  await page.getByRole("combobox", { name: "Package manager" }).selectOption("conda");
  await expect(command).toContainText("conda env update -n brightway-tested -f https://");
  await expect(page).toHaveURL(/check=conda-forge-/);
  const status = page.getByRole("list", { name: "Check results on Linux" });
  await expect(status).toContainText("conda-forge · Python 3.12 Passed");
  await expect(status).not.toContainText("Upstream test suites");
  // That check's caveats come with its command, such as the packages conda-forge lacks.
  const conda = (await guidanceFixture()).checks.find((c) => c.id.startsWith("conda-forge-"));
  await expect(page.locator(".install-set .caveats li")).toHaveText(conda?.caveats ?? []);
  await expect(page.locator(".install-files a").first()).toHaveText("environment.yml");
  await page.getByRole("combobox", { name: "Package manager" }).selectOption("pixi");
  await expect(command).toContainText("pixi install --frozen");
  await page.reload();
  await expect(page.getByRole("combobox", { name: "Package manager" })).toHaveValue("pixi");
  await page.getByRole("combobox", { name: "Operating system" }).selectOption("windows");
  await expect(page.getByText("No pixi set has passed on Windows on Python 3.12.", { exact: false })).toBeVisible();
});

test("the phone masthead scrolls the current page into view", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("?page=explorer");
  const nav = page.getByRole("navigation", { name: "Main", exact: true });
  const current = nav.getByRole("link", { name: "Benchmarks" });
  await expect(current).toHaveAttribute("aria-current", "page");
  const [box, link] = [await nav.boundingBox(), await current.boundingBox()];
  if (!box || !link) throw new Error("no masthead");
  expect(link.x + link.width).toBeLessThanOrEqual(box.x + box.width);
});

test("a benchmark's tab title uses its readable name", async ({ page }) => {
  await chart(page, SCORES);
  const name = await page.locator(".view > header h2").textContent();
  await expect.poll(async () => (await page.title()).startsWith(`${name} · `)).toBe(true);
});

test("phone checks show only the selected platform and keep check selection working", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("?platform=linux");
  const checks = page.getByRole("list", { name: "Linux checks" });
  await expect(checks).toBeVisible();
  await expect(
    page.getByRole("table", { name: "Compatibility checks by platform and Python version" }),
  ).not.toBeVisible();
  await checks.getByRole("link", { name: "Linux · Pre-releases Python 3.14 Passed" }).click();
  await expect(page.locator(".install-set > .install-command pre")).toContainText("pre-3.14");
  await page.getByRole("combobox", { name: "Operating system" }).selectOption("windows");
  await expect(page.getByRole("list", { name: "Linux checks" })).toHaveCount(0);
  await expect(page.getByRole("list", { name: "Windows checks" })).toBeVisible();
});

test("phone parameter details are optional while controls and the plot stay visible", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await chart(page, SCORES);
  await expect(page.getByLabel("Functional units", { exact: true })).toBeVisible();
  await expect(page.locator(".field-note:visible")).toHaveCount(0);
  const plot = await page.locator(".chart svg").boundingBox();
  expect(plot ? plot.y + plot.height / 2 : Infinity).toBeLessThan(844);
  await page.getByText("Parameter details", { exact: true }).click();
  await expect(page.locator(".parameter-details")).toContainText("26,533");
  await expect(page.locator(".parameter-details .field-note").first()).toBeVisible();
  await page.getByLabel("Scoring", { exact: true }).selectOption("adjoint");
  await expect(page.locator(".parameter-details")).toContainText("FastScoresOnlyMultiLCA");
  await page.setViewportSize({ width: 1440, height: 900 });
  await expect(page.getByText("Parameter details", { exact: true })).not.toBeVisible();
  await expect(page.locator(".controls .field-note").first()).toBeVisible();
});

test("new uv projects get a complete copyable setup for the selected Python and set", async ({ page, context }) => {
  await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  await page.goto("?platform=linux");
  await page.getByText("Starting a new project?", { exact: true }).click();
  const start = page.locator(".new-project");
  await expect(start.locator("pre")).toContainText(
    "uv init --no-package --python 3.12 brightway-project\ncd brightway-project\nuv add",
  );
  await start.getByRole("button", { name: "Copy project setup" }).click();
  const copied = await page.evaluate(() => navigator.clipboard.readText());
  expect(copied).toBe(await start.locator("pre").textContent());
  await page.getByRole("link", { name: "Linux · Python 3.14, Pre-releases: Passed" }).click();
  await expect(start.locator("pre")).toContainText("uv init --no-package --python 3.14");
  await expect(start.locator("pre")).toContainText("pre-3.14-ubuntu-latest/");
  await page.getByRole("combobox", { name: "Package manager" }).selectOption("conda");
  await expect(start).toHaveCount(0);
});

test("the page publishes a favicon and Open Graph metadata", async ({ page, request }) => {
  await page.goto("/");
  const icon = page.locator("link[rel='icon'][type='image/svg+xml']");
  await expect(icon).toHaveAttribute("href", /favicon\.svg$/);
  const ogImage = page.locator("meta[property='og:image']");
  await expect(ogImage).toHaveAttribute("content", /og\.png$/);

  const iconRes = await request.get("/favicon.svg");
  expect(iconRes.status()).toBe(200);
  expect(iconRes.headers()["content-type"]).toBe("image/svg+xml");

  const ogRes = await request.get("/og.png");
  expect(ogRes.status()).toBe(200);
  expect(ogRes.headers()["content-type"]).toBe("image/png");
});
