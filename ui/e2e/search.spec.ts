import { expect, type Page, test } from "@playwright/test";

// The masthead search on the static pages, and what one Enter does.
const STATIC = ["/findings/", "/about/", "/stories/solver-choice/"];
const SIZES = [
  { width: 1440, height: 900 },
  { width: 390, height: 844 },
];

async function openSearch(page: Page) {
  const field = page.getByRole("searchbox", { name: "Search" });
  if (!(await field.isVisible())) await page.getByRole("button", { name: "Show the search" }).click();
  return field;
}

for (const size of SIZES) {
  for (const path of STATIC) {
    test(`${path} at ${size.width}px lists results as you type, over the page`, async ({ page }) => {
      await page.setViewportSize(size);
      await page.goto(path);
      const field = await openSearch(page);
      await field.pressSequentially("solver");
      const hit = page.locator('.search-results a[href*="/stories/"]').first();
      await expect(hit).toBeVisible();
      await expect(page).toHaveURL(new RegExp(`${path}$`));
      // Nothing on the page draws over the open list.
      const covered = await page.locator(".search-results").evaluate((list) => {
        const box = list.getBoundingClientRect();
        const xs = [box.left + 4, box.left + box.width / 2, box.right - 4];
        const ys = [box.top + 4, box.top + box.height / 2, box.bottom - 4];
        return xs.flatMap((x) => ys.map((y) => document.elementFromPoint(x, y))).filter((el) => !list.contains(el))
          .length;
      });
      expect(covered).toBe(0);
    });
  }
}

test("a static page's search lists benchmarks too", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/about/");
  await (await openSearch(page)).fill("bw2calc multilca");
  await expect(page.locator(".search-results").getByRole("link", { name: /^MultiLCA/ })).toHaveCount(2);
});

test("Enter on a static page opens the first benchmark, and only that", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/findings/");
  const field = await openSearch(page);
  await field.fill("timeraw_import_bw2calc");
  await expect(page.locator(".search-results a").first()).toBeVisible();
  await field.press("Enter");
  await expect(page.locator(".benchmark-id")).toContainText("bench_import.timeraw_import_bw2calc");
  await expect(page).not.toHaveURL(/[?&]q=/);
  await expect(page.locator(".search-results")).toBeHidden();
});

test("Enter on a static page opens the first page hit when no benchmark matches", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/about/");
  const field = await openSearch(page);
  await field.fill("solver");
  await field.press("Enter");
  await expect(page).toHaveURL(/\/(stories|findings)\/[^?]*$/);
});

test("words handed to Benchmarks filter the catalogue without opening the results", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/?page=explorer&q=multi");
  await expect(page.locator(".rail-found")).toHaveText(/^\d+ benchmarks?$/);
  await expect(page.getByRole("searchbox", { name: "Search" })).toHaveValue("multi");
  await expect(page.locator(".search-results")).toBeHidden();
});

test("the results stay closed until there is something to list", async ({ page }) => {
  let answer = () => {};
  const held = new Promise<void>((resolve) => {
    answer = resolve;
  });
  await page.route("**/pagefind/pagefind.js", async (route) => {
    await held;
    await route.continue();
  });
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/");
  await page.locator("#main").waitFor();
  const field = page.getByRole("searchbox", { name: "Search" });
  // No benchmark matches and Pagefind has not answered: no empty box under the field.
  await field.fill("solver");
  await page.waitForTimeout(300);
  await expect(page.locator(".search-results")).toBeHidden();
  answer();
  await expect(page.locator('.search-results a[href*="/stories/"]').first()).toBeVisible();
});
