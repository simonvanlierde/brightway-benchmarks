import { expect, test } from "@playwright/test";

test("the header stays focused and desktop install selectors share a row", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("?platform=linux");
  await page.locator(".install-set > .install-command").waitFor();
  await expect(page.locator(".top").getByRole("link", { name: /^Checked / })).toHaveCount(0);
  await expect(page.locator(".checks-date")).toHaveText(/^Checked \w{3} \d{1,2}, \d{4} · open the run$/);
  await expect(page.locator(".checks-date a")).toHaveText("open the run");
  await expect(page.locator(".top .build-version, .top .github-link")).toHaveCount(0);
  const os = await page.getByRole("combobox", { name: "Operating system" }).boundingBox();
  const python = await page.getByRole("combobox", { name: "Python version" }).boundingBox();
  const manager = await page.getByRole("combobox", { name: "Package manager" }).boundingBox();
  expect(os && python && manager).toBeTruthy();
  expect(Math.abs((os?.y ?? 0) - (manager?.y ?? 999))).toBeLessThan(3);
  expect(Math.abs((python?.y ?? 0) - (manager?.y ?? 999))).toBeLessThan(3);
});

test("desktop check help shares a row and uses the column labels", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("?platform=linux");
  const caption = page.locator(".check-help");
  await expect(caption).toContainText("Select a result");
  // At 1440 the grid fits its column, so there is nothing to scroll and no hint.
  await expect(caption.getByText("Scroll to see all check types")).toBeHidden();
  // Narrower, it scrolls: the hint shows on the same row, and the grid's right edge is shaded.
  await page.setViewportSize({ width: 1000, height: 900 });
  await expect(caption.getByText("Scroll to see all check types")).toBeVisible();
  await expect(page.getByRole("region", { name: "Check grid" })).toHaveClass(/overflowing/);
  const hint = await caption.locator("span").last().boundingBox();
  const section = await page.locator(".all-checks").boundingBox();
  expect(hint && section && hint.x + hint.width <= section.x + section.width).toBe(true);
  const definitions = page.locator(".check-kinds dt");
  await expect(definitions).toHaveText([
    "Latest releases",
    "Dependency floors",
    "Pre-releases",
    "conda-forge",
    "Upstream test suites",
  ]);
});

test("the check grid never scrolls vertically", async ({ page }) => {
  for (const width of [1280, 1440, 1920]) {
    await page.setViewportSize({ width, height: 1000 });
    await page.goto("?platform=linux");
    const grid = page.locator(".scroll.desktop-checks");
    await grid.locator(".check-grid").waitFor();
    const [scroll, client] = await grid.evaluate((e) => [e.scrollHeight, e.clientHeight]);
    expect(scroll, `${width}px`).toBeLessThanOrEqual(client);
  }
});

test("on a phone the install command wraps at spaces, never inside a flag", async ({ page }) => {
  for (const width of [320, 390]) {
    await page.setViewportSize({ width, height: 900 });
    await page.goto("?platform=linux");
    const command = page.locator(".install-set > .install-command code");
    await command.waitFor();
    // Each flag starts a box, and its first characters ("-c h") sit on one line.
    const flags = await command.locator(".word").evaluateAll((words) =>
      words
        .filter((w) => w.textContent?.startsWith("-"))
        .map((w) => {
          const range = document.createRange();
          const text = w.querySelector(".part")?.firstChild as Text;
          range.setStart(text, 0);
          range.setEnd(text, Math.min(4, text.length));
          return new Set([...range.getClientRects()].map((r) => Math.round(r.top))).size;
        }),
    );
    expect(flags.length).toBeGreaterThan(0);
    expect(flags.every((lines) => lines === 1)).toBe(true);
    // A long URL breaks after a "/" only: each piece between them sits on one line.
    const pieces = await command.locator(".part").evaluateAll((parts) =>
      parts.map((p) => {
        const range = document.createRange();
        range.selectNodeContents(p);
        return new Set([...range.getClientRects()].map((r) => Math.round(r.top))).size;
      }),
    );
    expect(pieces.every((lines) => lines === 1)).toBe(true);
    // The words are the command's own, so selecting and copying it by hand gives the same text.
    const text = await command.textContent();
    expect(text).toMatch(/ -c https:/);
  }
});

test("Setup's heading and intro draw before the viewer's script runs, and only on Setup", async ({ page }) => {
  await page.route("**/_astro/App.*.js", (route) => route.abort());
  await page.goto("./");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("A tested Brightway setup");
  await expect(page.locator(".home-intro p")).toContainText("Every night we test which Brightway releases install");
  await page.goto("?page=explorer");
  await expect(page.locator(".home-intro")).toHaveCount(0);
});

test("the landing page is as tall as its content, with the footer in view after it", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("?platform=linux");
  await page.locator(".nudges").waitFor();
  const footer = page.locator(".site-footer");
  await expect(footer).toBeInViewport({ ratio: 1 });
  const gap = await page.evaluate(() => {
    const columns = [...document.querySelectorAll(".home-columns > *")].map((c) => c.getBoundingClientRect().bottom);
    return (document.querySelector(".site-footer")?.getBoundingClientRect().top ?? 0) - Math.max(...columns);
  });
  // The view's own bottom padding, not a viewport-tall minimum height.
  expect(gap).toBeLessThan(80);
});

test("Setup does not shift as its script and data arrive", async ({ page }) => {
  await page.addInitScript(() => {
    const w = window as unknown as { shifts: number };
    w.shifts = 0;
    new PerformanceObserver((list) => {
      for (const e of list.getEntries()) w.shifts += (e as PerformanceEntry & { value: number }).value;
    }).observe({ type: "layout-shift", buffered: true });
  });
  // Each data file late, so the page paints its loading states first.
  await page.route("**/data/*.json", async (route) => {
    await new Promise((done) => setTimeout(done, 300));
    await route.continue();
  });
  for (const width of [390, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    await page.goto("?platform=linux");
    await page.locator(".nudges").waitFor();
    await expect(page.locator(".site-footer")).toBeAttached();
    expect(await page.evaluate(() => (window as unknown as { shifts: number }).shifts), `${width}px`).toBeLessThan(
      0.001,
    );
  }
});
