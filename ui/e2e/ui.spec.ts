import AxeBuilder from "@axe-core/playwright";
import { expect, type Page, test } from "@playwright/test";

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
    ["light", "light", 1280, 900],
    ["dark", "dark", 1280, 900],
    ["phone", "light", 375, 812],
    ["phone-dark", "dark", 375, 812],
  ] as const) {
    test(name, async ({ page }) => {
      await page.setViewportSize({ width, height });
      await page.emulateMedia({ colorScheme: scheme });
      await chart(page, SCORES);
      await page.locator(".chart").focus();
      await page.keyboard.press("End");
      await page.getByText(/^Data table/).click();
      await page.evaluate(() => scrollTo(0, 0));
      await page.screenshot({ path: `${shots}/bench-${name}.png`, fullPage: true });
      // Nothing wider than the screen: the tables scroll inside their own box.
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      await page.goto("./");
      await expect(page.getByRole("heading", { name: "What moved in the latest releases" })).toBeVisible();
      await page.screenshot({ path: `${shots}/start-${name}.png`, fullPage: true });
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
  await page.getByRole("link", { name: "bench_import.timeraw_import_bw2calc" }).first().click();
  await expect(page.getByRole("main").getByRole("heading", { level: 2 })).toHaveText(
    "bench_import.timeraw_import_bw2calc",
  );
  await page.goBack();
  await expect(page.getByLabel("variant", { exact: true })).toHaveValue("adjoint");
});

test("the start page links each change to its chart", async ({ page }) => {
  await page.goto("./");
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
  await expect(changes.getByText("level shift (Otava)").first()).toBeVisible();
  await expect(changes.getByText("release vs. noise").first()).toBeVisible();
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
  await page.goto("./");
  await expect(page.getByRole("alert")).toContainText("HTTP 404");
});

for (const scheme of ["light", "dark"] as const) {
  for (const [where, url] of [
    ["start", "./"],
    ["benchmark", SCORES],
  ] as const) {
    test(`axe: no WCAG 2.2 AA violations, ${where}, ${scheme}`, async ({ page }) => {
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
