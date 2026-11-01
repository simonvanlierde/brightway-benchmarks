import { readFile } from "node:fs/promises";
import AxeBuilder from "@axe-core/playwright";
import { expect, type Page, test } from "@playwright/test";
import type { Guidance } from "../src/lib/contract";
import { latestChanges } from "../src/lib/history";

// Screenshots go to SHOTS when it is set, so a reviewer can look at them; CI keeps them as an artifact.
const shots = process.env.SHOTS ?? "test-results/shots";
const IMPORT = "?bench=bw2calc-bench-import-timeraw-import-bw2calc-c078f5d2c0be";
const SCORES = "?bench=bw2calc-bench-lca-multiscores-time-scores-4f172f3e24a0&p=ecoinvent&p=3&p=MultiLCA";

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
      await expect(page.getByRole("heading", { name: "What moved in the latest releases" })).toBeVisible();
      await page.screenshot({ path: `${shots}/start-${name}.png`, fullPage: true });
      await page.screenshot({ path: `${shots}/start-${name}-viewport.png` });
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    });
  }
});

test("the view lives in the URL, and back goes back", async ({ page }) => {
  await chart(page, SCORES);
  await page.getByLabel("variant", { exact: true }).selectOption("adjoint");
  await expect(page).toHaveURL(/p=adjoint/);
  await page.reload();
  await expect(page.getByLabel("variant", { exact: true })).toHaveValue("adjoint");
  await expect(page.getByLabel("demands", { exact: true })).toHaveValue("3");
  await page.getByRole("link", { name: "Import bw2calc" }).first().click();
  await expect(page.getByRole("main").getByRole("heading", { level: 2 })).toHaveText("Import bw2calc");
  await page.goBack();
  await expect(page.getByLabel("variant", { exact: true })).toHaveValue("adjoint");
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
  await expect(page.getByRole("status")).toContainText("1 of 15 reports did not load");
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
  await expect(page.getByLabel("size", { exact: true })).toHaveCount(0);
  await expect(page.locator(".fixed")).toHaveText("ecoinvent");
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
  await expect(page.getByRole("heading", { level: 3 })).toHaveText(["Regressions", "Improvements"]);
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

test("the explorer opens on the newest regression", async ({ page }) => {
  const index = JSON.parse(await readFile(new URL("../test/fixtures/real/index.json", import.meta.url), "utf8"));
  const worst = latestChanges(index).find((r) => r.way === "worse");
  await page.goto("?page=explorer");
  await expect(page.getByRole("main").locator("code").first()).toHaveText(worst?.bench.name ?? "");
  await expect(page.locator(".chart svg")).toBeVisible();
});

test("the explorer explains the benchmark and the chosen parameter values", async ({ page }) => {
  await page.goto("?page=explorer");
  await expect(page.locator(".bench-about")).not.toBeEmpty();
  const notes = page.locator(".param-notes");
  const cls = page.getByLabel("cls", { exact: true });
  if ((await cls.count()) === 0) test.skip(true, "the newest regression has no cls choice");
  await cls.selectOption("JacobiGMRESLCA");
  await expect(notes).toContainText("JacobiGMRESLCA: Solves by GMRES");
  await cls.selectOption("LCA");
  await expect(notes).toContainText("LCA: Solves directly");
});

test("clearing a shared package filter stays on release changes", async ({ page }) => {
  // A link from before the page parameter: the filters alone chose the changes page.
  await page.goto("?group=bw-processing-dfb1fd2e3103");
  const heading = page.getByRole("heading", { name: "What moved in the latest releases" });
  await expect(heading).toBeVisible();
  await expect(page.getByRole("status")).toHaveText("3 of 3 changes shown");
  await page.getByLabel("Package", { exact: true }).selectOption({ label: "All packages" });
  await expect(heading).toBeVisible();
  await expect(page).toHaveURL(/page=changes/);
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
  await expect(page.getByRole("heading", { name: "What moved in the latest releases" })).toBeVisible();
  await expect(page.locator("#main")).toBeFocused();
});

test("catalogue search accepts readable names and original identifiers", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto("?page=explorer");
  const search = page.getByRole("searchbox", { name: "Find a benchmark" });
  await search.fill("Multi Scores");
  await expect(page.getByRole("navigation", { name: "Benchmarks" }).locator("li a")).toHaveCount(2);
  await search.fill("timeraw_import_bw2calc");
  await expect(page.getByRole("navigation", { name: "Benchmarks" }).locator("li a")).toHaveCount(2);
  await search.fill("missing-case");
  await expect(page.getByText("No benchmarks match")).toBeVisible();
  await search.fill("");
  await page
    .getByRole("navigation", { name: "Benchmarks" })
    .getByRole("link", { name: "Import bw2calc" })
    .first()
    .click();
  await expect(page.locator(".benchmark-id")).toContainText("bench_import.timeraw_import_bw2calc");
});

test("an unknown benchmark link names the problem", async ({ page }) => {
  await page.goto("?bench=missing-case");
  await expect(page.getByRole("status")).toContainText("This benchmark is not in the current data");
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

test("home separates tested setups, compatibility and benchmark evidence", async ({ page }) => {
  await page.goto("./");
  const main = page.getByRole("navigation", { name: "Main", exact: true });
  await expect(main.getByRole("link", { name: "Home", exact: true })).toBeVisible();
  await expect(main.getByRole("link", { name: "Compatibility", exact: true })).toBeVisible();
  await expect(main.getByRole("link", { name: "Release changes", exact: true })).toBeVisible();
  await expect(main.getByRole("link", { name: "Benchmark explorer", exact: true })).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Benchmarks", exact: true })).toHaveCount(0);
  await main.getByRole("link", { name: "Compatibility", exact: true }).click();
  await expect(page).toHaveURL(/page=compatibility/);
  await page.goBack();
  await expect(main.getByRole("link", { name: "Home", exact: true })).toHaveAttribute("aria-current", "page");
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
      await page.getByRole("link", { name: "Download requirements.txt", exact: true }).waitFor();
      await page.screenshot({ path: `${shots}/home-${name}-viewport.png` });
      await page.screenshot({ path: `${shots}/home-${name}.png`, fullPage: true });
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      await page
        .getByRole("navigation", { name: "Main", exact: true })
        .getByRole("link", { name: "Compatibility", exact: true })
        .click();
      await page.locator(".compat-table tbody tr").first().waitFor();
      await page.screenshot({ path: `${shots}/compatibility-${name}-viewport.png` });
      await page.screenshot({ path: `${shots}/compatibility-${name}.png`, fullPage: true });
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    });
  }
});

const guidanceFixture = async (): Promise<Guidance> =>
  JSON.parse(await readFile(new URL("../test/fixtures/real/guidance.json", import.meta.url), "utf8"));

test("platform setups keep their pins, install command and URL together", async ({ page }) => {
  const data = await guidanceFixture();
  await page.goto("?page=home&platform=linux");
  const windows = data.platforms.find((p) => p.id === "windows");
  const check = data.checks.find((c) => c.id === windows?.defaultCheck);
  if (!windows || !check?.lastPassed?.install) throw new Error("fixture lacks a Windows setup");
  await page.getByRole("button", { name: windows.label, exact: true }).click();
  await expect(page).toHaveURL(/platform=windows/);
  await expect(page.locator(".install-command pre")).toHaveText(check.lastPassed.install);
  await expect(page.getByRole("link", { name: "Download requirements.txt", exact: true })).toHaveAttribute(
    "href",
    check.lastPassed.files.find((f) => f.label === "requirements.txt")?.url ?? "",
  );
  await page.reload();
  await expect(page.getByRole("button", { name: windows.label, exact: true })).toHaveAttribute("aria-pressed", "true");
  await page.goBack();
  await expect(page.getByRole("button", { name: "Linux", exact: true })).toHaveAttribute("aria-pressed", "true");
});

test("compatibility selection and filters survive shared URLs and back", async ({ page }) => {
  await page.goto("?page=compatibility");
  await page.getByLabel("Platform", { exact: true }).selectOption("linux");
  await page.getByLabel("Python", { exact: true }).selectOption("3.12");
  const suites = page.locator(".compat-table tbody tr").filter({ hasText: "Upstream test suites" });
  await suites.getByRole("link").first().click();
  await expect(page).toHaveURL(/check=suites-/);
  await expect(page.getByRole("complementary", { name: "Selected check" })).toContainText(
    "Upstream test suites · Failed",
  );
  const link = page.url();
  await page.reload();
  await expect(page.getByLabel("Platform", { exact: true })).toHaveValue("linux");
  await expect(page.getByLabel("Python", { exact: true })).toHaveValue("3.12");
  await expect(page.getByRole("complementary", { name: "Selected check" })).toContainText(
    "Upstream test suites · Failed",
  );
  await page
    .getByRole("navigation", { name: "Main", exact: true })
    .getByRole("link", { name: "Home", exact: true })
    .click();
  await expect(page).toHaveTitle(/^Home ·/);
  await page.goBack();
  await expect(page).toHaveURL(link);
  await expect(page).toHaveTitle(/^Compatibility ·/);
});

test("a failed current check keeps its older passing files clearly dated", async ({ page }) => {
  const data = await guidanceFixture();
  const current = data.checks.find((c) => c.id === data.platforms.find((p) => p.id === "linux")?.defaultCheck);
  if (!current?.lastPassed) throw new Error("fixture lacks Linux saved set");
  current.status = "failure";
  current.lastPassed.date = "2026-10-30";
  await page.route("**/data/guidance.json", (route) => route.fulfill({ json: data }));
  await page.goto("?page=home&platform=linux");
  await expect(page.locator(".check-outcome")).toHaveText("Smoke calculations · Failed");
  await expect(page.getByText("The current check did not pass.")).toBeVisible();
  await expect(page.locator(".saved-header")).toContainText("Oct 30, 2026");
  await expect(page.getByRole("link", { name: "Download requirements.txt", exact: true })).toBeVisible();
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
    await expect(page.getByRole("link", { name: "Download requirements.txt", exact: true })).toHaveCount(0);
    if (status !== 404) await expect(page.getByRole("status")).toContainText("Setup guidance could not be loaded");
    await page
      .getByRole("navigation", { name: "Main", exact: true })
      .getByRole("link", { name: "Benchmark explorer", exact: true })
      .click();
    await expect(page.locator(".chart svg")).toBeVisible();
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

test("legacy compatibility anchors open the compatibility tab", async ({ page }) => {
  await page.goto("./#works-together");
  await expect(
    page
      .getByRole("navigation", { name: "Main", exact: true })
      .getByRole("link", { name: "Compatibility", exact: true }),
  ).toHaveAttribute("aria-current", "page");
  await expect(page).toHaveTitle(/^Compatibility ·/);
});

test("phone check selection reveals and focuses the saved environment", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("?page=compatibility&platform=linux&python=3.12");
  await page
    .locator(".compat-table tbody tr")
    .filter({ hasText: "Upstream test suites" })
    .getByRole("link")
    .first()
    .click();
  await expect(page.locator("#selected-check")).toBeFocused();
  const box = await page.locator("#selected-check").boundingBox();
  expect(box?.y ?? -1).toBeGreaterThanOrEqual(0);
  expect(box?.y ?? 1000).toBeLessThan(844);
});

for (const scheme of ["light", "dark"] as const) {
  for (const width of [1440, 390]) {
    for (const route of ["home", "compatibility"]) {
      test(`guidance axe: ${route}, ${scheme}, ${width}px`, async ({ page }) => {
        await page.setViewportSize({ width, height: 900 });
        await page.emulateMedia({ colorScheme: scheme });
        await page.goto(`?page=${route}&platform=linux`);
        await page.getByRole("link", { name: "Download requirements.txt", exact: true }).waitFor();
        const result = await new AxeBuilder({ page })
          .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa", "best-practice"])
          .analyze();
        expect(result.violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target).join(" | ")}`)).toEqual([]);
      });
    }
  }
}

test("a conda environment offers its manifest and lock before other files", async ({ page }) => {
  await page.goto("?page=compatibility");
  await page.locator(".compat-table tbody tr").filter({ hasText: "conda-forge" }).getByRole("link").first().click();
  const detail = page.getByRole("complementary", { name: "Selected check" });
  await expect(detail.locator(".primary-action")).toHaveText("Download pixi.toml");
  await expect(detail.getByRole("link", { name: "pixi.lock", exact: true })).toBeVisible();
  await expect(detail.locator(".install-command pre")).toContainText("pixi");
});
