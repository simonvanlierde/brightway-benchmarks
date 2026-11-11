import { expect, test } from "@playwright/test";

test("the header stays focused and desktop install selectors share a row", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("?platform=linux");
  await page.locator(".install-set > .install-command").waitFor();
  await expect(page.locator(".top").getByRole("link", { name: /^Checked / })).toHaveCount(0);
  await expect(page.locator(".checks-date")).toHaveText(/^Checked \w{3} \d{1,2}, \d{4} · open the run$/);
  await expect(page.locator(".checks-date a")).toHaveText("open the run");
  await expect(page.locator(".top .build-version, .top .github-link")).toHaveCount(0);
  const os = await page.getByRole("combobox", { name: "Operating system" }).boundingBox();
  const python = await page.getByRole("combobox", { name: "Python version" }).boundingBox();
  const manager = await page.getByRole("combobox", { name: "Package manager" }).boundingBox();
  expect(os && python && manager).toBeTruthy();
  expect(Math.abs((os?.y ?? 0) - (manager?.y ?? 999))).toBeLessThan(3);
  expect(Math.abs((python?.y ?? 0) - (manager?.y ?? 999))).toBeLessThan(3);
});

test("desktop check help shares a row and uses the column labels", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("?platform=linux");
  const caption = page.locator(".check-help");
  await expect(caption).toContainText("Select a check");
  // At 1440 the grid fits its column, so there is nothing to scroll and no hint.
  await expect(caption.getByText("Scroll to see all check types")).toBeHidden();
  // Narrower, it scrolls: the hint shows on the same row, and the grid's right edge is shaded.
  await page.setViewportSize({ width: 1000, height: 900 });
  await expect(caption.getByText("Scroll to see all check types")).toBeVisible();
  await expect(page.getByRole("region", { name: "Check grid" })).toHaveClass(/overflowing/);
  const hint = await caption.locator("span").last().boundingBox();
  const section = await page.locator(".all-checks").boundingBox();
  expect(hint && section && hint.x + hint.width <= section.x + section.width).toBe(true);
  const definitions = page.locator(".check-kinds dt");
  await expect(definitions).toHaveText([
    "Latest releases",
    "Dependency floors",
    "Pre-releases",
    "conda-forge",
    "Upstream test suites",
  ]);
});
