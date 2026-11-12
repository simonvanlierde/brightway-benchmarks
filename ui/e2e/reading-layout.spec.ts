import { expect, test } from "@playwright/test";

test("reading pages fit a narrow phone without JavaScript", async ({ browser }) => {
  const context = await browser.newContext({
    javaScriptEnabled: false,
    viewport: { width: 320, height: 800 },
    reducedMotion: "reduce",
  });
  const page = await context.newPage();
  for (const route of ["stories/solver-choice/", "stories/home-heating/", "findings/", "about/"]) {
    await page.goto(route);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), route).toBe(true);
  }
  await context.close();
});
