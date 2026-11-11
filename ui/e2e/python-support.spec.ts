import { readFile } from "node:fs/promises";
import { expect, test } from "@playwright/test";

test("Setup shows each package on Python 3.11 to 3.15 with the failure and its reason", async ({ page }) => {
  await page.goto("");
  const section = page.getByRole("region", { name: "Python versions grid" });
  const table = section.getByRole("table");
  await expect(table.getByRole("columnheader")).toHaveText([
    "Package and system",
    "Python",
    "3.11",
    "3.12",
    "3.13",
    "3.14",
    "3.15",
  ]);
  await expect(table.getByRole("row")).toHaveCount(11); // two header rows and three packages on three systems
  const failed = table.getByRole("link", { name: "bw_timex, Windows, Python 3.15: Failed" });
  await expect(failed).toHaveText("Failed");
  await expect(failed).toHaveAttribute("href", /actions\/runs\/\d+/);
  await expect(table.getByRole("link", { name: "brightway25, Linux, Python 3.13: Pass" })).toHaveText("Pass");
  const reasons = page.locator(".python-support .support-failures");
  // The line naming what failed comes before its reason.
  await expect(reasons.locator("dt")).toHaveText(
    "Python 3.15 on Linux, macOS and Windows: brightway25, bw_graph_tools and bw_timex",
  );
  await expect(reasons.locator("dd")).toContainText("Failed to build `cachebox==5.2.3`");
  // The end-of-life lines are the maintainers' view.
  await expect(page.getByRole("heading", { name: "End-of-life Pythons" })).toHaveCount(0);
});

test("Benchmarks shows the end-of-life Pythons on Linux", async ({ page }) => {
  await page.goto("?page=explorer");
  const table = page.getByRole("region", { name: "End-of-life Pythons grid" }).getByRole("table");
  await expect(table.getByRole("columnheader")).toHaveText(["Package", "Python", "3.9", "3.10"]);
  await expect(table.getByRole("link", { name: "bw_graph_tools, Python 3.9: Failed" })).toBeVisible();
  await expect(table.getByRole("link", { name: "brightway25, Python 3.10: Failed" })).toBeVisible();
  await expect(page.locator(".python-support .support-failures")).toContainText("stdout_feedback_logger");
});

test("a result the data lacks shows as not checked, in the full grid", async ({ page }) => {
  const data = JSON.parse(await readFile(new URL("../test/fixtures/real/guidance.json", import.meta.url), "utf8"));
  data.pythonSupport.results = data.pythonSupport.results.filter(
    (r: { python: string; platform: string }) => !(r.python === "3.12" && r.platform === "macos"),
  );
  await page.route("**/data/guidance.json", (route) => route.fulfill({ json: data }));
  await page.goto("");
  const table = page.getByRole("region", { name: "Python versions grid" }).getByRole("table");
  await expect(table.getByRole("row")).toHaveCount(11);
  const row = table.getByRole("row").filter({ hasText: "bw_timex macOS" });
  await expect(row.getByRole("cell")).toHaveCount(5);
  await expect(row.getByRole("cell").nth(1)).toHaveText(/–\s*not checked/);
  await expect(row.getByRole("cell").nth(1).getByRole("link")).toHaveCount(0);
});

test("on a phone the table breaks only between words and the page does not scroll sideways", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 800 });
  await page.goto("");
  const grid = page.getByRole("region", { name: "Python versions grid" });
  await grid.scrollIntoViewIfNeeded();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  // A cell has at most one line per word (package names break at their underscores): more means a split word.
  const split = await grid.evaluate((el) =>
    [...el.querySelectorAll("thead th, tbody a, tbody th code")]
      .filter((node) => {
        const range = document.createRange();
        range.selectNodeContents(node);
        const lines = new Set([...range.getClientRects()].map((r) => Math.round(r.top))).size;
        return lines > (node.textContent ?? "").trim().split(/[\s_]+/).length;
      })
      .map((node) => node.textContent),
  );
  expect(split).toEqual([]);
});
