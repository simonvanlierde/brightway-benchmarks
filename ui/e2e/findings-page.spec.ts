import { readFileSync } from "node:fs";
import { expect, test } from "@playwright/test";
import { parse } from "smol-toml";

const listed = (parse(readFileSync("../benchmarks/findings.toml", "utf8")) as { findings: Record<string, unknown>[] })
  .findings;
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
  await expect(items.getByRole("heading", { level: 2 })).toHaveText(listed.map((f) => String(f.title)));
  const stories = await items
    .getByRole("link", { name: /^Read the story/ })
    .evaluateAll((as) => as.map((a) => a.getAttribute("href") ?? ""));
  expect(stories).toEqual(listed.filter((f) => f.story).map((f) => `/stories/${f.story}/`));
  for (const href of stories) expect((await request.get(href)).ok(), href).toBe(true);
  // Each history link opens the view the viewer's own finding card opens.
  const views = await items.locator("h2 a").evaluateAll((as) => as.map((a) => a.getAttribute("href") ?? ""));
  expect(views).toHaveLength(published.findings.length);
  for (const [i, href] of views.entries()) {
    const want = [...(published.findings[i]?.params ?? [])];
    while (want.at(-1) === "") want.pop();
    expect(new URLSearchParams(href.slice(href.indexOf("?"))).getAll("p"), href).toEqual(want);
    await page.goto(href);
    await expect(page.locator(".chart svg"), href).toBeVisible();
  }
});

test("Setup's and Benchmarks' finding cards end with one link to all findings", async ({ page }) => {
  for (const path of ["", "?page=explorer"]) {
    await page.goto(path);
    const all = page.locator(".findings").getByRole("link", { name: "All findings" });
    await expect(all, path).toHaveCount(1);
    await expect(all).toHaveAttribute("href", "/findings/");
  }
});
