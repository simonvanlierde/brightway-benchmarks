import { expect, test } from "@playwright/test";

test("Setup shows each package on Python 3.11 to 3.15 with the failure and its reason", async ({ page }) => {
  await page.goto("");
  const section = page.getByRole("region", { name: "Python versions grid" });
  const table = section.getByRole("table");
  await expect(table.getByRole("columnheader")).toHaveText([
    "Package and system",
    "Python 3.11",
    "Python 3.12",
    "Python 3.13",
    "Python 3.14",
    "Python 3.15",
  ]);
  await expect(table.getByRole("row")).toHaveCount(10); // header and three packages on three systems
  const failed = table.getByRole("link", { name: "bw_timex, Windows, Python 3.15: Failed" });
  await expect(failed).toHaveText("Failed");
  await expect(failed).toHaveAttribute("href", /actions\/runs\/\d+/);
  await expect(table.getByRole("link", { name: "brightway25, Linux, Python 3.13: Pass" })).toHaveText("Pass");
  const reasons = page.locator(".python-support .support-failures");
  await expect(reasons).toContainText("Failed to build `cachebox==5.2.3`");
  await expect(reasons).toContainText("Python 3.15 on Linux, macOS and Windows");
  // The end-of-life lines are the maintainers' view.
  await expect(page.getByRole("heading", { name: "End-of-life Pythons" })).toHaveCount(0);
});

test("Benchmarks shows the end-of-life Pythons on Linux", async ({ page }) => {
  await page.goto("?page=explorer");
  const table = page.getByRole("region", { name: "End-of-life Pythons grid" }).getByRole("table");
  await expect(table.getByRole("columnheader")).toHaveText(["Package", "Python 3.9", "Python 3.10"]);
  await expect(table.getByRole("link", { name: "bw_graph_tools, Python 3.9: Failed" })).toBeVisible();
  await expect(table.getByRole("link", { name: "brightway25, Python 3.10: Failed" })).toBeVisible();
  await expect(page.locator(".python-support .support-failures")).toContainText("stdout_feedback_logger");
});

test("the table scrolls on a phone without widening the page", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 800 });
  await page.goto("");
  await page.getByRole("region", { name: "Python versions grid" }).scrollIntoViewIfNeeded();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});
