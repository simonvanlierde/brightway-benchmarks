import { readFile } from "node:fs/promises";
import { expect, test } from "@playwright/test";

test("Setup shows each package on Python 3.11 to 3.15 with the failure and its reason", async ({ page }) => {
  await page.goto("");
  const section = page.locator(".python-support");
  const table = page.getByRole("region", { name: "Python versions grid" }).getByRole("table");
  // One header row; each version's header says Python to a screen reader.
  await expect(table.getByRole("columnheader")).toHaveText([
    "Package and system",
    "Python 3.11",
    "Python 3.12",
    "Python 3.13",
    "Python 3.14",
    "Python 3.15",
  ]);
  await expect(table.getByRole("row")).toHaveCount(10); // a header row and three packages on three systems
  // The lead line comes from the data, and the run is linked once, beside the date.
  await expect(section.locator(".support-lead")).toHaveText(
    "3.11 to 3.14 work on every system. 3.15 does not install yet: a dependency (cachebox) fails to build.",
  );
  await expect(section.locator(".support-date")).toHaveText(/^Checked \w{3} \d{1,2}, \d{4} · open the run$/);
  await expect(section.locator(".support-date a")).toHaveAttribute("href", /actions\/runs\/\d+/);
  // Only a failed cell is a link: nine of them, not 45 tab stops.
  await expect(table.getByRole("link")).toHaveCount(9);
  const failed = table.getByRole("link", { name: "bw_timex, Windows, Python 3.15: Failed" });
  await expect(failed).toHaveText("Failed");
  await expect(failed).toHaveAttribute("href", /actions\/runs\/\d+/);
  const passed = table.getByRole("row").filter({ hasText: "brightway25 Linux" }).getByRole("cell").nth(2);
  await expect(passed).toHaveText("Passed");
  const reasons = section.locator(".support-failures");
  // The line naming what failed comes before its reason.
  await expect(reasons.locator("dt")).toHaveText(
    "Python 3.15 on Linux, macOS and Windows: brightway25, bw_graph_tools and bw_timex",
  );
  // The quoted name shows as code, without the backticks.
  await expect(reasons.locator("dd")).toContainText("Failed to build cachebox==5.2.3:");
  await expect(reasons.locator("dd code").first()).toHaveText("cachebox==5.2.3");
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
  // No release of bw_timex declares 3.9: not a failure, so no failure line, and the legend says so.
  // Not a link and not a smaller font: the same cell as Passed, in the muted tone.
  const undeclared = table.getByRole("row").filter({ hasText: "bw_timex" }).getByRole("cell").first();
  await expect(undeclared).toHaveText("Not declared");
  await expect(undeclared.getByRole("link")).toHaveCount(0);
  const size = (cell: typeof undeclared) => cell.locator("span").evaluate((e) => getComputedStyle(e).font);
  const passed = table.getByRole("row").filter({ hasText: "bw_timex" }).getByRole("cell").nth(1);
  expect(await size(undeclared)).toBe(await size(passed));
  await expect(page.locator(".python-support .support-failures")).not.toContainText("bw-timex");
  await expect(page.getByText("Not declared: no release of the package supports that Python")).toBeVisible();
});

test("a result the data lacks shows as not checked, in the full grid", async ({ page }) => {
  const data = JSON.parse(await readFile(new URL("../test/fixtures/real/guidance.json", import.meta.url), "utf8"));
  data.pythonSupport.results = data.pythonSupport.results.filter(
    (r: { python: string; platform: string }) => !(r.python === "3.12" && r.platform === "macos"),
  );
  await page.route("**/data/guidance.json", (route) => route.fulfill({ json: data }));
  await page.goto("");
  const table = page.getByRole("region", { name: "Python versions grid" }).getByRole("table");
  await expect(table.getByRole("row")).toHaveCount(10);
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
