import { expect, type Page, test } from "@playwright/test";

const FIRST_SCORE = "?bench=bw2calc-bench-lca-singlescore-time-first-score-0523b3edee8d&p=ecoinvent&p=LCA";
const MULTI = "?bench=bw2calc-bench-lca-multiscores-time-scores-4f172f3e24a0&p=ecoinvent&p=3&p=MultiLCA";

async function chart(page: Page, url: string) {
  await page.goto(url);
  await page.locator(".chart svg").waitFor();
}

test("a chart chunk that failed to load is fetched again for the next benchmark", async ({ page }) => {
  // After a deploy the old chunk is gone: the first try fails, the next benchmark must not reuse that failure.
  await page.route("**/HistoryChart.*.js", (route) => route.fulfill({ status: 404 }));
  await page.goto(FIRST_SCORE);
  const alert = page.getByRole("alert");
  await expect(alert).toContainText("The chart did not load. Reload the page.");
  await expect(alert.getByText("Technical details")).toBeVisible();
  await page.unroute("**/HistoryChart.*.js");
  await page.getByRole("link", { name: "MultiLCA" }).first().click();
  await expect(page.locator(".chart svg")).toBeVisible();
});

test("the chart's code is requested with the benchmark's reports, before they arrive", async ({ page }) => {
  let reportsDone = false;
  let chunkAsked: boolean | undefined;
  page.on("requestfinished", (r) => {
    if (/\/data\/.+\/.+\.json$/.test(r.url())) reportsDone = true;
  });
  await page.route("**/data/*/**/*.json", async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 500)); // slow reports
    await route.continue();
  });
  page.on("request", (r) => {
    if (/HistoryChart\.[\w-]+\.js$/.test(r.url())) chunkAsked ??= !reportsDone;
  });
  await chart(page, FIRST_SCORE);
  expect(chunkAsked).toBe(true);
});

test("a scroll region takes keyboard focus only while it has something to scroll", async ({ page }) => {
  const focusable = () => page.locator('[role="region"][tabindex="0"]');
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("?platform=linux");
  await page.locator(".python-support").waitFor();
  await expect(focusable()).toHaveCount(0);
  await page.setViewportSize({ width: 320, height: 800 });
  await expect(focusable()).toHaveCount(1);
  await expect(focusable()).toHaveAttribute("aria-label", "Python versions grid");
});

test("the data files are preloaded from the page, and fetched once", async ({ page }) => {
  const asked: string[] = [];
  page.on("request", (r) => {
    if (/\/data\/(index|guidance)\.json$/.test(r.url())) asked.push(new URL(r.url()).pathname);
  });
  await page.goto("");
  await page.locator(".install-set").waitFor();
  const preloads = await page
    .locator('link[rel="preload"][as="fetch"][crossorigin]')
    .evaluateAll((links) => links.map((l) => l.getAttribute("href")));
  expect(preloads).toEqual(["data/index.json", "data/guidance.json"]);
  expect(asked.filter((p) => p.endsWith("index.json"))).toHaveLength(1);
  expect(asked.filter((p) => p.endsWith("guidance.json"))).toHaveLength(1);
});

test("an empty check-grid cell is a hidden dash with text for a screen reader", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("?platform=linux");
  const grid = page.getByRole("region", { name: "Check grid" });
  await expect(grid.locator("td span[aria-label]")).toHaveCount(0);
  const empty = grid.getByRole("row").filter({ hasText: "Linux · Python 3.13" }).getByRole("cell").nth(1);
  await expect(empty).toHaveText(/–\s*not checked/);
  await expect(empty.locator('[aria-hidden="true"]')).toHaveText("–");
});

test("without guidance, Setup's heading is the site's name, as the masthead shows it", async ({ page }) => {
  await page.route("**/data/guidance.json", (route) => route.fulfill({ status: 404 }));
  await page.goto("");
  await expect(page.getByRole("main").getByRole("heading", { level: 2 }).first()).toHaveText("Brightway Benchmarks");
});

test("Setup's intro quotes the solver table's own figures", async ({ page }) => {
  await page.goto("");
  const cells = page.locator(".solver-evidence tbody td.num");
  await expect(cells).toHaveCount(3);
  const [umfpack, , superlu] = await cells.allTextContents();
  const intro = page.locator(".home-intro p").first();
  await expect(intro).toContainText(`takes ${superlu}`);
  await expect(intro).toContainText(`it takes ${umfpack}`);
});

test("the skip link stays out of view at a larger text size until it has focus", async ({ page }) => {
  await page.goto("stories/solver-choice/");
  await page.evaluate(() => {
    document.documentElement.style.fontSize = "200%";
  });
  const skip = page.locator(".skip");
  expect(((await skip.boundingBox())?.y ?? 0) + ((await skip.boundingBox())?.height ?? 0)).toBeLessThanOrEqual(0);
  await page.keyboard.press("Tab");
  await expect(skip).toBeFocused();
  await expect.poll(async () => (await skip.boundingBox())?.y ?? -1).toBeGreaterThanOrEqual(0);
});

test("Copy and Copy latest are drawn as one kind of button", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("?platform=linux");
  const look = (name: string) =>
    page.getByRole("button", { name, exact: true }).evaluate((b) => {
      const s = getComputedStyle(b);
      return [s.borderLeftColor, s.fontWeight, s.fontSize]; // Copy has only a left border, inside the frame
    });
  expect(await look("Copy latest")).toEqual(await look("Copy"));
});

test("the solver story's commands copy", async ({ page, context }) => {
  await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  await page.goto("stories/solver-choice/");
  const box = page.locator(".install");
  await expect(box.getByRole("button", { name: "Copy" })).toHaveCount(4);
  await box.getByRole("button", { name: "Copy" }).nth(1).click();
  await expect(box.getByRole("status")).toHaveText("Copied the command");
  expect(await page.evaluate(() => navigator.clipboard.readText())).toBe("conda install -c conda-forge scikit-umfpack");
});

test("a solver's story bar has the colour its line has on the chart", async ({ page }) => {
  const hex = (rgb: string) =>
    `#${(rgb.match(/\d+/g) ?? []).map((n) => Number(n).toString(16).padStart(2, "0")).join("")}`;
  await page.goto("stories/solver-choice/");
  const bar = page.locator(".bars li").filter({ hasText: "Nothing extra (SciPy's SuperLU)" }).first().locator(".fill");
  const story = hex(await bar.evaluate((r) => getComputedStyle(r).fill));
  await chart(page, "?bench=bw2calc-conda-bench-lca-singlescore-time-first-scor-7266cbe9fcd4&p=ecoinvent&p=LCA");
  const strokes = await page
    .locator('.chart :is([data-mark="line"], [data-mark="dot"]) path')
    .evaluateAll((paths) => paths.map((p) => p.getAttribute("stroke")));
  const legend = page.locator(".legend-host button", { hasText: "SuperLU" });
  await expect(legend).toHaveCount(1);
  expect(strokes).toContain(story);
});

test("the x axis names a commit that is not a release, muted; the y axis keeps one precision", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await chart(page, FIRST_SCORE);
  const ticks = page.locator('.chart [data-mark="x-axis tick label"] text');
  const unreleased = ticks.filter({ hasText: /^[0-9a-f]{8}$/ });
  await expect(unreleased).toHaveCount(1);
  const muted = await page.evaluate(() =>
    getComputedStyle(document.documentElement).getPropertyValue("--muted").trim(),
  );
  await expect(unreleased).toHaveAttribute("fill", muted);
  const y = await page.locator('.chart [data-mark="y-axis tick label"] text').allTextContents();
  const decimals = new Set(y.map((t) => t.split(".")[1]?.length ?? 0));
  expect(decimals.size, y.join(" ")).toBe(1);
});

test("on a phone, fifteen releases draw lines without per-point markers", async ({ page }) => {
  const markers = () => page.locator('.chart [data-mark="dot"] path').count();
  await page.setViewportSize({ width: 1440, height: 900 });
  await chart(page, FIRST_SCORE);
  expect(await markers()).toBeGreaterThan(0);
  await page.setViewportSize({ width: 390, height: 844 });
  await expect.poll(markers).toBe(0);
  await expect(page.locator('.chart :is([data-mark="line"], [data-mark="dot"]) path')).not.toHaveCount(0);
});

test("on a phone the build id is the footer's own last row", async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 800 });
  await page.goto(MULTI);
  const build = await page.locator(".build-version").boundingBox();
  const links = await page
    .locator(".site-footer a:not(.build-version)")
    .evaluateAll((as) => as.map((a) => a.getBoundingClientRect().bottom));
  expect(build?.y ?? 0).toBeGreaterThanOrEqual(Math.max(...links));
  expect(build?.x).toBe(
    await page
      .locator(".site-footer a")
      .first()
      .evaluate((a) => a.getBoundingClientRect().x),
  );
});
