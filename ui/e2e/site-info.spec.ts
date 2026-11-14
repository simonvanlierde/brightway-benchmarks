import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

const SITE = "https://simonvanlierde.com/brightway-benchmarks/";
// Platforms cache a preview by URL, so each card's URL carries its hash.
const card = (file: string) =>
  `${SITE}ui/${file}?v=${createHash("sha256")
    .update(readFileSync(`public/${file}`))
    .digest("hex")
    .slice(0, 8)}`;

test("the initial HTML describes the viewer and names its public canonical URL", async ({ request }) => {
  const html = await (await request.get("/")).text();
  expect(html).toContain("<title>Tested setups and release histories · Brightway Benchmarks</title>");
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

test("the solver story is static, links the viewer at exact views and has its own preview", async ({
  browser,
  request,
}) => {
  const context = await browser.newContext({ javaScriptEnabled: false });
  const page = await context.newPage();
  await page.goto("/stories/solver-choice/");
  await expect(page.getByRole("heading", { level: 1 })).toContainText("by about 5 times");
  await expect(page.locator('link[rel="canonical"]')).toHaveAttribute("href", `${SITE}stories/solver-choice/`);
  await expect(page.locator('meta[property="og:image"]')).toHaveAttribute("content", card("story-solver-choice.png"));
  const index = await (await request.get("/data/index.json")).json();
  const links = await page
    .locator('main a[href*="page=explorer"]')
    .evaluateAll((as) => as.map((a) => a.getAttribute("href") ?? ""));
  // Two chart links to the viewer and five inline links.
  expect(links).toHaveLength(7);
  for (const href of links) {
    const q = new URL(href, SITE).searchParams;
    const group = index.groups.find((g: { name: string }) => g.name === q.get("group"));
    expect(group, href).toBeDefined();
    const bench = index.benchmarks.find(
      (b: { group: string; name: string }) => b.group === group.id && b.name === q.get("bench"),
    );
    expect(bench, href).toBeDefined();
    const labels = q.getAll("p");
    expect(labels, href).toHaveLength(bench.params.length);
    const values = labels.map((label, i) => bench.params[i].values[bench.params[i].labels.indexOf(label)]);
    expect(values, href).not.toContain(undefined);
    const exists = index.cases.some(
      (c: { benchmark: string; params: string[] }) =>
        c.benchmark === bench.id && values.every((v, i) => c.params[i] === v),
    );
    expect(exists, href).toBe(true);
  }
  await context.close();
});

test("the heating story has its own preview card", async ({ request }) => {
  const html = await (await request.get("/stories/home-heating/")).text();
  expect(html).toContain(`property="og:image" content="${card("story-home-heating.png")}"`);
  expect((await request.get("/story-home-heating.png")).ok()).toBe(true);
});

test("every page's title is the page, then the site", async ({ request }) => {
  for (const path of ["/", "/about/", "/stories/solver-choice/", "/stories/home-heating/"]) {
    const title = (await (await request.get(path)).text()).match(/<title>([^<]*)<\/title>/)?.[1];
    expect(title, path).toMatch(/^[^·—:]+ · Brightway Benchmarks$/);
  }
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
