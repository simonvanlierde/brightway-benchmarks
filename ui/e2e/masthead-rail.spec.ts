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
  // The masthead drawn before the app runs is replaced when it mounts; measure the app's.
  await page.locator("#main").waitFor();
  const box = await page.locator("header.top").boundingBox();
  expect(box?.height).toBeLessThan(100);
});

test("the viewer draws its masthead before its script runs", async ({ browser }) => {
  const context = await browser.newContext({ javaScriptEnabled: false, viewport: { width: 1440, height: 900 } });
  const page = await context.newPage();
  await page.goto("/");
  const nav = page.getByRole("navigation", { name: "Main" });
  await expect(nav.getByRole("link")).toHaveText(["Setup", "Benchmarks", "Findings"]);
  await expect(page.getByRole("searchbox", { name: "Search" })).toBeVisible();
  // Enter before the app mounts hands the words over as ?q=, rather than dropping them.
  await page.getByRole("searchbox", { name: "Search" }).fill("multi");
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/[?&]q=multi$/);
  await context.close();
});

test("switching between Setup and Benchmarks moves neither the page nor the masthead links", async ({ page }) => {
  // Tall enough that Setup fits without a scrollbar while Benchmarks needs one.
  await page.setViewportSize({ width: 1440, height: 3000 });
  const measure = async (path: string) => {
    await page.goto(path);
    await page.locator("#main").waitFor();
    await page.locator(".view h2").first().waitFor();
    return page.evaluate(() => [
      document.documentElement.clientWidth,
      ...[...document.querySelectorAll(".primary-nav a")].map((a) => Math.round(a.getBoundingClientRect().x)),
    ]);
  };
  expect(await measure("?page=explorer")).toEqual(await measure("./"));
});

test("Setup does not scroll sideways at 900px", async ({ page }) => {
  await page.setViewportSize({ width: 900, height: 900 });
  await page.goto("?platform=linux");
  await page.locator(".install-set > .install-command").waitFor();
  const [scroll, client] = await page.evaluate(() => [
    document.documentElement.scrollWidth,
    document.documentElement.clientWidth,
  ]);
  expect(scroll).toBeLessThanOrEqual(client);
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

test("the package select fits at 200%", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 800 });
  await page.goto("?page=explorer");
  const select = page.locator("#package-filter");
  await expect(select).toBeVisible();
  // After the load: an init script runs before the parser makes <html>, and its style is lost.
  await page.evaluate(() => {
    document.documentElement.style.fontSize = "200%";
    // A wide font, as on a runner without the system UI font: narrower fonts hid the overflow.
    document.documentElement.style.fontFamily = '"DejaVu Sans", Verdana, sans-serif';
  });
  expect(await page.evaluate(() => getComputedStyle(document.documentElement).fontSize)).toBe("32px");
  const box = await select.boundingBox();
  expect((box?.x ?? 0) + (box?.width ?? 0)).toBeLessThanOrEqual(375);
  const [scroll, client] = await page.evaluate(() => [
    document.documentElement.scrollWidth,
    document.documentElement.clientWidth,
  ]);
  expect(scroll).toBeLessThanOrEqual(client);
  // The tables scroll inside their own box, so the page check above does not see them. The Python support
  // grid is left out: at this size it is wider than a phone and scrolls in its keyboard-focusable region.
  const clipped = await page
    .locator(".scroll:not(.python-support *)")
    .evaluateAll((els) => els.filter((e) => e.scrollWidth > e.clientWidth).length);
  expect(clipped).toBe(0);
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
  await page.locator(".latest-table tbody th a").first().click();
  const figure = page.locator("figure[aria-labelledby=reading-guide]");
  await expect(figure).toBeVisible();
  await expect(page.locator("#reading-guide")).toBeVisible();
});
