import { readFileSync } from "node:fs";
import { expect, test } from "@playwright/test";
import { parse } from "smol-toml";

const listed = (
  parse(readFileSync("../benchmarks/findings.toml", "utf8")) as {
    findings: { title: string; doc: string; story?: string }[];
  }
).findings;
const published = JSON.parse(readFileSync("test/fixtures/real/index.json", "utf8")) as {
  findings: { title: string; params: string[] }[];
};

test("the masthead has three items, and Findings is current on its page and on every story", async ({ page }) => {
  for (const [path, current] of <[string, string][]>[
    ["", "Setup"],
    ["?page=explorer", "Benchmarks"],
    ["findings/", "Findings"],
    ["stories/solver-choice/", "Findings"],
    ["stories/home-heating/", "Findings"],
  ]) {
    await page.goto(path);
    const nav = page.getByRole("navigation", { name: "Main" });
    await expect(nav.getByRole("link"), path).toHaveText(["Setup", "Benchmarks", "Findings"]);
    await expect(nav.locator('[aria-current="page"]'), path).toHaveText(current);
  }
});

test("the findings page lists every finding, and each link opens what it names", async ({ page, request }) => {
  await page.goto("findings/");
  const items = page.locator(".finding-list > li");
  // findings.toml lists them in the write-up's order, which groups them by package.
  await expect(items.getByRole("heading", { level: 4 })).toHaveText(listed.map((f) => f.title));
  // A headline opens its story where it has one, its write-up otherwise.
  const titles = await items.locator("h4 a").evaluateAll((as) => as.map((a) => a.getAttribute("href") ?? ""));
  expect(titles).toEqual(listed.map((f) => (f.story ? `/stories/${f.story}/` : `#${f.doc}`)));
  for (const href of titles.filter((h) => h.startsWith("/"))) expect((await request.get(href)).ok(), href).toBe(true);
  // Each history link opens the view the viewer's own finding card opens.
  const views = await items
    .getByRole("link", { name: /^Open the history/ })
    .evaluateAll((as) => as.map((a) => a.getAttribute("href") ?? ""));
  expect(views).toHaveLength(published.findings.length);
  for (const [i, href] of views.entries()) {
    const want = [...(published.findings[i]?.params ?? [])];
    while (want.at(-1) === "") want.pop();
    expect(new URLSearchParams(href.slice(href.indexOf("?"))).getAll("p"), href).toEqual(want);
    await page.goto(href);
    await expect(page.locator(".chart svg"), href).toBeVisible();
  }
});

test("the findings page carries each write-up, and a headline's link lands on it", async ({ page }) => {
  await page.goto("findings/");
  for (const f of listed) await expect(page.locator(`.writeups h3#${f.doc}`), f.doc).toHaveCount(1);
  // The write-up's links to repository files open on GitHub, not as paths on this site.
  const relative = await page
    .locator(".writeups a")
    .evaluateAll((as) => as.map((a) => a.getAttribute("href") ?? "").filter((h) => !/^(https?:|#|\/)/.test(h)));
  expect(relative).toEqual([]);
  const first = listed.find((f) => f.story) as (typeof listed)[number];
  await page.getByRole("link", { name: `Write-up on ${first.title}` }).click();
  await expect(page).toHaveURL(new RegExp(`#${first.doc}$`));
  await expect(
    page.locator(`#${first.doc} + .finding-links`).getByRole("link", { name: "Open the history" }),
  ).toBeVisible();
});

test("a wide findings page has an outline of every write-up beside it", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("findings/");
  const outline = page.getByRole("navigation", { name: "Findings" });
  for (const f of listed) await expect(outline.locator(`a[href="#${f.doc}"]`), f.doc).toHaveCount(1);
  await page.locator(".writeups h3").nth(4).scrollIntoViewIfNeeded();
  await expect(outline.getByRole("link", { name: "Headlines" })).toBeInViewport();
  // The outline replaces the package bar; a narrow page keeps the bar instead.
  await expect(page.getByRole("navigation", { name: "Write-ups by package" })).toBeHidden();
  await page.setViewportSize({ width: 390, height: 900 });
  await expect(outline).toBeHidden();
  await expect(page.getByRole("navigation", { name: "Write-ups by package" })).toBeVisible();
});

test("Benchmarks' intro links to all findings", async ({ page }) => {
  await page.goto("?page=explorer");
  const all = page.locator(".overview-intro").getByRole("link", { name: "what the benchmarks found" });
  await expect(all).toHaveCount(1);
  await expect(all).toHaveAttribute("href", "/findings/");
  await expect(page.locator(".findings")).toHaveCount(0);
});
