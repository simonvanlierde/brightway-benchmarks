import { expect, test } from "@playwright/test";

const SITE = "https://simonvanlierde.com/brightway-benchmarks/";
const IMAGE = `${SITE}ui/og.png`;

for (const path of ["/", "/about/"]) {
  test(`${path} initial HTML includes one canonical and complete sharing metadata`, async ({ browser }) => {
    const context = await browser.newContext({ javaScriptEnabled: false });
    const page = await context.newPage();
    await page.goto(path);
    const canonical = path === "/" ? SITE : `${SITE}about/`;
    await expect(page.locator('link[rel="canonical"]')).toHaveCount(1);
    await expect(page.locator('link[rel="canonical"]')).toHaveAttribute("href", canonical);
    await expect(page.locator('meta[property="og:url"]')).toHaveCount(1);
    await expect(page.locator('meta[property="og:url"]')).toHaveAttribute("content", canonical);
    for (const selector of ['meta[property="og:image"]', 'meta[name="twitter:image"]']) {
      await expect(page.locator(selector)).toHaveCount(1);
      await expect(page.locator(selector)).toHaveAttribute("content", IMAGE);
    }
    await expect(page.locator('meta[property="og:image:width"]')).toHaveAttribute("content", "1200");
    await expect(page.locator('meta[property="og:image:height"]')).toHaveAttribute("content", "630");
    await expect(page.locator('meta[property="og:image:type"]')).toHaveAttribute("content", "image/png");
    await expect(page.locator('meta[name="twitter:card"]')).toHaveAttribute("content", "summary_large_image");
    const alt = await page.locator('meta[property="og:image:alt"]').getAttribute("content");
    expect(alt?.length).toBeGreaterThan(20);
    await expect(page.locator('meta[name="twitter:image:alt"]')).toHaveAttribute("content", alt ?? "");
    await context.close();
  });
}

test("sharing images and icons are served at the homepage and ui paths", async ({ request }) => {
  for (const asset of ["favicon.svg", "favicon.ico", "apple-touch-icon.png", "og.png"]) {
    for (const prefix of ["/", "/ui/"]) {
      const response = await request.get(`${prefix}${asset}`);
      expect(response.ok(), `${prefix}${asset}`).toBe(true);
      expect(response.headers()["content-type"]).toMatch(/^image\//);
    }
  }
  // Keep the request local while checking the exact path used by public metadata.
  const image = await request.get(new URL(IMAGE).pathname.replace("/brightway-benchmarks", ""));
  const bytes = await image.body();
  expect(bytes.subarray(0, 8).toString("hex")).toBe("89504e470d0a1a0a");
  expect(bytes.readUInt32BE(16)).toBe(1200);
  expect(bytes.readUInt32BE(20)).toBe(630);
});
