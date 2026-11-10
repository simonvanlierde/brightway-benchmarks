import { expect, test } from "@playwright/test";

test("a rail group is named for its package, and filtering announces the count", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("?page=explorer&q=multi");
  const rail = page.getByRole("navigation", { name: "Benchmarks" });
  const list = rail.getByRole("list").first();
  const label = (await list.getAttribute("aria-label")) ?? "";
  expect(label).toMatch(/^\S+$/);
  const snapshot = await rail.ariaSnapshot();
  expect(snapshot).toMatch(new RegExp(`group: ${label} \\(\\d+\\)|${label} \\(\\d+\\)`));
  expect(snapshot).not.toMatch(/[▸▾]/);
  await expect(page.locator(".rail-status")).toHaveAttribute("role", "status");
  await expect(page.locator(".rail-found")).toHaveText(/^\d+ benchmarks?$/);
  await page.locator("#benchmark-search").fill("zzzz-no-match");
  await expect(page.locator(".rail-status .rail-empty")).toContainText("No benchmarks match");
});

test("the masthead is one short row at tablet width", async ({ page }) => {
  await page.setViewportSize({ width: 768, height: 900 });
  await page.goto("?page=explorer");
  const box = await page.locator("header.top").boundingBox();
  expect(box?.height).toBeLessThan(100);
});

test("Setup does not scroll sideways at 900px", async ({ page }) => {
  await page.setViewportSize({ width: 900, height: 900 });
  await page.goto("?platform=linux");
  await page.locator(".install-set > .install-command").waitFor();
  const [scroll, client] = await page.evaluate(() => [
    document.documentElement.scrollWidth,
    document.documentElement.clientWidth,
  ]);
  expect(scroll).toBe(client);
});

test("the phone search toggle closes while the field has text", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 800 });
  await page.goto("?page=explorer&q=multi");
  const toggle = page.locator(".search-toggle");
  await expect(toggle).toHaveAttribute("aria-expanded", "true");
  await toggle.click();
  await expect(toggle).toHaveAttribute("aria-expanded", "false");
  await expect(page.locator(".masthead-search")).toBeHidden();
});

test("the package filter stays inside the viewport with a large root font", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 800 });
  await page.addInitScript(() => {
    document.documentElement.style.fontSize = "200%";
  });
  await page.goto("?page=explorer");
  const filter = page.locator(".package-filter");
  if (await filter.count()) {
    const box = await filter.first().boundingBox();
    expect((box?.x ?? 0) + (box?.width ?? 0)).toBeLessThanOrEqual(375);
  }
});

test("a static page's nav fits at 320px", async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 800 });
  await page.goto("stories/home-heating/");
  const nav = page.locator(".primary-nav");
  const [scroll, client] = await nav.evaluate((el) => [el.scrollWidth, el.clientWidth]);
  expect(scroll).toBeLessThanOrEqual(client);
});

test("the chart is named by its reading guide, not the whole caption", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("?page=explorer");
  await page.locator(".findings h3 a").first().click();
  const figure = page.locator("figure[aria-labelledby=reading-guide]");
  await expect(figure).toBeVisible();
  await expect(page.locator("#reading-guide")).toBeVisible();
});
