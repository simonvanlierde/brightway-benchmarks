import { expect, type Page, test } from "@playwright/test";

// The policy is a <meta> that Astro writes into each page (astro.config.mjs). A blocked script,
// style, image or request shows up as a console error and a securitypolicyviolation event.
const IMPORT = "?bench=bw2calc-bench-import-timeraw-import-bw2calc-c078f5d2c0be";
const PAGES = [
  "/",
  IMPORT,
  "?page=changes",
  "?page=compatibility",
  "/about/",
  "/stories/solver-choice/",
  "/stories/home-heating/",
];

async function watch(page: Page) {
  const problems: string[] = [];
  page.on("console", (m) => m.type() === "error" && problems.push(`console: ${m.text()}`));
  page.on("pageerror", (e) => problems.push(`pageerror: ${e.message}`));
  await page.addInitScript(() =>
    document.addEventListener("securitypolicyviolation", (e) =>
      console.error(`violation: ${e.violatedDirective} blocked ${e.blockedURI || "inline"}`),
    ),
  );
  return problems;
}

for (const url of PAGES) {
  test(`CSP blocks nothing on ${url}`, async ({ page }) => {
    const problems = await watch(page);
    await page.goto(url);
    await expect(page.locator('meta[http-equiv="content-security-policy"]')).toHaveCount(1);
    await page.waitForLoadState("networkidle");
    expect(problems).toEqual([]);
    await page.locator("[data-theme-toggle]").first().click();
    if (url.includes("bench=")) {
      await page.locator(".chart svg").waitFor();
      await page.mouse.move(400, 400);
      await page.getByText(/^Data table/).click();
      const [download] = await Promise.all([
        page.waitForEvent("download"),
        page.getByRole("button", { name: "Download SVG" }).click(),
      ]);
      expect(download.suggestedFilename()).toMatch(/\.svg$/);
    }
    await page.waitForLoadState("networkidle");
    expect(problems).toEqual([]);
  });
}

test("the search form on a static page submits under the policy", async ({ page }) => {
  const problems = await watch(page);
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/about/");
  await page.getByRole("searchbox", { name: "Search" }).fill("multi");
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/\/\?page=explorer&q=multi$/);
  // The explorer has loaded its data and drawn, so a block on the new page would have shown by now.
  await expect(page.locator(".latest-table tbody th a").first()).toBeVisible();
  // The words arrive with their results open, and Pagefind's WebAssembly runs under the policy.
  await expect(
    page
      .locator(".search-results")
      .getByRole("list")
      .filter({ has: page.locator('a[href*="/findings/"], a[href*="/stories/"], a[href*="/about/"]') })
      .getByRole("link")
      .first(),
  ).toBeVisible();
  await page.waitForLoadState("networkidle");
  expect(problems).toEqual([]);
});
