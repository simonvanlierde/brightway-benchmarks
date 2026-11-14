import AxeBuilder from "@axe-core/playwright";
import { expect, type Page, test } from "@playwright/test";

// Screenshots go to SHOTS when it is set, as in ui.spec.ts.
const shots = process.env.SHOTS ?? "test-results/shots";

async function accessible(page: Page) {
  const result = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa", "best-practice"])
    .analyze();
  expect(result.violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target).join(" ")}`)).toEqual([]);
}

test("Across machines reads one row per machine under each choice, with its summary", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("?page=compare");
  await expect(page).toHaveTitle(/^Across machines · /);
  // It belongs to Benchmarks: the masthead marks Benchmarks, and the catalogue stays beside it.
  await expect(
    page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Benchmarks" }),
  ).toHaveAttribute("aria-current", "page");
  const solvers = page.getByRole("region", { name: "Solver", exact: true }).getByRole("table");
  await expect(solvers.getByRole("columnheader")).toHaveText([
    "Machine",
    "Source",
    "Ratio",
    "95% interval",
    /Interval drawn around 1$/, // the words faster and slower above the graphic are hidden from a screen reader
    "Reading",
  ]);
  // The rowgroup header names the choice and its range over the machines where the difference is clear.
  const pardiso = solvers.getByRole("rowgroup").filter({ hasText: "PyPardiso against SuperLU" });
  await expect(pardiso.locator(".ratio-summary")).toHaveText("1.21 to 19.9x slower on 2 machines, 2 OSes");
  const windows = pardiso.getByRole("row").filter({ hasText: "GitHub win25-vs2026" });
  await expect(windows.getByRole("cell").nth(1)).toHaveText("19.9");
  await expect(windows.getByRole("cell").nth(2)).toHaveText("19.1 to 20.5");
  await expect(windows.getByRole("cell").last()).toContainText("19.9x slower");
  // A missing arm is no result, with its reason, never a zero.
  const mac = pardiso.getByRole("row").filter({ hasText: "GitHub macos26" });
  await expect(mac.getByRole("cell").nth(1)).toHaveText("–");
  await expect(mac.getByRole("cell").last()).toContainText("Not measured");
  await expect(mac.getByRole("cell").last()).toContainText("pypardiso did not install");
  // Hosted rows link the run that wrote them.
  await expect(windows.getByRole("link", { name: /the run$/ })).toHaveAttribute("href", /actions\/runs\/43604589027$/);
  await expect(windows).toContainText("Hosted");
  // Directions that disagree say so.
  const python = page.getByRole("region", { name: "Python version", exact: true });
  await expect(
    python.getByRole("rowgroup").filter({ hasText: "Python 3.12 against" }).locator(".ratio-summary"),
  ).toHaveText("Depends on platform: faster on 1 machine, slower on 1");
  await page.screenshot({ path: `${shots}/comparisons-light.png`, fullPage: true });
  await accessible(page);
});

test("Benchmarks and Setup link to the comparisons", async ({ page }) => {
  await page.goto("?page=explorer");
  await page.getByRole("link", { name: "compare it across machines" }).click();
  await expect(page.getByRole("heading", { level: 2, name: "Across machines" })).toBeVisible();
  await page.goto("");
  await expect(page.getByRole("link", { name: "Does it hold on your machine?" })).toHaveAttribute(
    "href",
    "?page=compare",
  );
});

test("Without published ratios, the page says so and Benchmarks offers no link", async ({ page }) => {
  await page.route("**/data/ratios.json", (route) => route.fulfill({ status: 404, body: "" }));
  await page.goto("?page=compare");
  await expect(page.locator("#main .empty")).toHaveText(/^No comparisons are published yet\./);
  await page.goto("?page=explorer");
  await expect(page.getByRole("heading", { level: 2, name: "Benchmarks" })).toBeVisible();
  await expect(page.getByRole("link", { name: "compare it across machines" })).toHaveCount(0);
});

for (const colorScheme of ["light", "dark"] as const) {
  test(`Across machines fits a phone in ${colorScheme} mode and passes axe`, async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.emulateMedia({ colorScheme });
    await page.goto("?page=compare");
    await expect(page.locator(".ratio-row").first()).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: `${shots}/comparisons-phone-${colorScheme}.png`, fullPage: true });
    await accessible(page);
  });
}

test("Across machines in dark mode on a laptop passes axe", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.emulateMedia({ colorScheme: "dark" });
  await page.goto("?page=compare");
  await expect(page.locator(".ratio-row").first()).toBeVisible();
  await page.screenshot({ path: `${shots}/comparisons-dark.png`, fullPage: true });
  await accessible(page);
});
