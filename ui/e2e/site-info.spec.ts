import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

const SITE = "https://simonvanlierde.com/brightway-benchmarks/";

test("the initial HTML describes the viewer and names its public canonical URL", async ({ request }) => {
  const html = await (await request.get("/")).text();
  expect(html).toContain("<title>Brightway benchmarks: tested setups and release histories</title>");
  expect(html).toContain('name="description"');
  expect(html).toContain(`rel="canonical" href="${SITE}"`);
  expect(html).toContain('property="og:title"');
  expect(html).toContain('name="robots" content="index,follow"');
});

test("the static About page explains evidence and browser storage without JavaScript", async ({ browser }) => {
  const context = await browser.newContext({ javaScriptEnabled: false });
  const page = await context.newPage();
  await page.goto("/about/");
  await expect(page.getByRole("heading", { name: "About these benchmarks" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Privacy" })).toBeVisible();
  await expect(page.getByRole("main")).toContainText("package-manager and theme preferences");
  await expect(page.getByRole("main")).toContainText("IP addresses");
  await expect(page.locator('link[rel="canonical"]')).toHaveAttribute("href", `${SITE}about/`);
  await context.close();
});

test("the solver story is static, links the viewer at exact views and has its own preview", async ({ browser }) => {
  const context = await browser.newContext({ javaScriptEnabled: false });
  const page = await context.newPage();
  await page.goto("/stories/solver-choice/");
  await expect(page.getByRole("heading", { level: 1 })).toContainText("2.6 s or 28 s");
  await expect(page.locator('link[rel="canonical"]')).toHaveAttribute("href", `${SITE}stories/solver-choice/`);
  await expect(page.locator('meta[property="og:image"]')).toHaveAttribute(
    "content",
    `${SITE}ui/story-solver-choice.png`,
  );
  const bars = page.locator("figure.bars a");
  await expect(bars).toHaveCount(6);
  const href = (await bars.first().getAttribute("href")) ?? "";
  for (const part of [
    "page=explorer",
    "group=bw2calc-conda",
    "bench=bench_lca.SingleScore.time_first_score",
    "p=ecoinvent&p=LCA",
  ]) {
    expect(href).toContain(part);
  }
  await context.close();
});

test("the sitemap and icon are published without listing transient benchmark selections", async ({ request }) => {
  const sitemap = await request.get("/sitemap.xml");
  expect(sitemap.ok()).toBe(true);
  const xml = await sitemap.text();
  expect(xml).toContain(`<loc>${SITE}</loc>`);
  expect(xml).toContain(`<loc>${SITE}about/</loc>`);
  expect(xml).toContain(`<loc>${SITE}stories/solver-choice/</loc>`);
  expect(xml).not.toContain("?bench=");
  const icon = await request.get("/favicon.svg");
  expect(icon.ok()).toBe(true);
  expect(await icon.text()).toContain("<svg");
});

for (const colorScheme of ["light", "dark"] as const) {
  test(`About is readable and accessible on a phone in ${colorScheme} mode`, async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.emulateMedia({ colorScheme });
    await page.goto("/about/");
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    const result = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa", "best-practice"])
      .analyze();
    expect(result.violations.map((v) => v.id)).toEqual([]);
  });
}
