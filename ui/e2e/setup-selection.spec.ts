import { readFile } from "node:fs/promises";
import { expect, test } from "@playwright/test";
import type { Guidance } from "../src/lib/contract";

const command = ".install-set > .install-command";
const condaCheck = "conda-forge-3.12-ubuntu-latest";
const preCheck = "pre-3.14-ubuntu-latest";

test("selecting a conda check opens its own install set", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("?platform=linux");
  await page.locator(`.check-grid a[href*="check=${condaCheck}"]`).click();
  await expect(page).toHaveURL(new RegExp(`check=${condaCheck}`));
  await expect(page.locator(`${command} pre`)).toContainText("conda env update");
  await expect(page.locator(`${command} pre`)).toContainText("/compat/conda-forge-");
  await expect(page.getByLabel("Package manager", { exact: true })).toHaveValue("conda");
  await page.reload();
  await expect(page.locator(`${command} pre`)).toContainText("/compat/conda-forge-");
});

test("the selected check cell is not drawn with the focus outline", async ({ page }) => {
  await page.goto(`?platform=linux&check=${condaCheck}`);
  const cell = page.locator(`.check-grid a[href*="check=${condaCheck}"]`);
  await expect(cell).toHaveCSS("outline-style", "none");
  await expect(cell).not.toHaveCSS("box-shadow", "none");
  await cell.focus();
  await page.keyboard.press("Tab");
  await page.keyboard.press("Shift+Tab");
  await expect(cell).toHaveCSS("outline-style", "solid");
});

test("the footer names the project links, not the pages the masthead and Findings reach", async ({ page }) => {
  await page.goto("?platform=linux");
  const links = page.locator(".site-footer").getByRole("link");
  await expect(links).toHaveText(["Method", "Cite", "GitHub", "About & privacy", /./]);
  await page.goto("about/");
  await expect(page.locator(".site-footer").getByRole("link")).toHaveText([
    "Method",
    "Cite",
    "GitHub",
    "About & privacy",
  ]);
});

test("an explicit check replaces an incompatible remembered manager", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("bwbench.manager", "conda"));
  await page.goto(`?platform=linux&check=${preCheck}`);
  await expect(page.locator(`${command} pre`)).toContainText(`/compat/${preCheck}/`);
  await expect(page.getByLabel("Package manager", { exact: true })).toHaveValue("uv");
});

test("a selected check without a passing set never falls back to latest releases", async ({ page }) => {
  await page.goto("?platform=linux&check=suites-3.12-ubuntu-latest");
  await expect(page.locator(command)).toHaveCount(0);
  await expect(page.locator(".no-saved")).toContainText("Upstream test suites");
  await expect(page.locator(".no-saved")).toContainText("Python 3.12");
});

test("manual manager changes select the check behind the command", async ({ page }) => {
  await page.goto("?platform=linux");
  await page.getByLabel("Package manager", { exact: true }).selectOption("conda");
  await expect(page).toHaveURL(new RegExp(`check=${condaCheck}`));
  await expect(page.locator(`${command} pre`)).toContainText("/compat/conda-forge-");
  await expect(page.locator(`.check-grid a[href*="check=${condaCheck}"]`)).toHaveAttribute("aria-current", "true");
  await page.getByLabel("Operating system", { exact: true }).selectOption("windows");
  await expect(page).toHaveURL(/platform=windows/);
  await expect(page.getByText("No conda set has passed on Windows on Python 3.12.", { exact: false })).toBeVisible();
  await expect(page.getByLabel("Package manager", { exact: true })).toHaveValue("conda");
  await page.goBack();
  await expect(page).toHaveURL(new RegExp(`check=${condaCheck}`));
  await expect(page.locator(`${command} pre`)).toContainText("/compat/conda-forge-");
  await page.getByLabel("Package manager", { exact: true }).selectOption("uv");
  await expect(page).toHaveURL(/check=latest-3\.12-ubuntu-latest/);
  await expect(page.locator(`${command} pre`)).toContainText("/compat/latest-3.12-");
});

test("choosing Python keeps its URL and never installs another Python's manager set", async ({ page }) => {
  await page.goto("?platform=linux&check=floors-3.12-ubuntu-latest");
  await page.getByLabel("Python version", { exact: true }).selectOption("3.14");
  await expect(page).toHaveURL(/check=latest-3\.14-ubuntu-latest/);
  await expect(page.locator(`${command} pre`)).toContainText("/compat/latest-3.14-");
  await page.reload();
  await expect(page.getByLabel("Python version", { exact: true })).toHaveValue("3.14");
  await page.getByLabel("Package manager", { exact: true }).selectOption("conda");
  await expect(page).toHaveURL(/check=latest-3\.14-ubuntu-latest/);
  await expect(page.getByLabel("Python version", { exact: true })).toHaveValue("3.14");
  await expect(page.getByLabel("Package manager", { exact: true })).toHaveValue("conda");
  await expect(page.locator(command)).toHaveCount(0);
  await expect(page.locator(".no-saved")).toContainText("Linux on Python 3.14");
});

test("manager changes preserve an explicitly selected Python version", async ({ page }) => {
  await page.goto("?platform=linux&check=latest-3.14-ubuntu-latest");
  await page.getByLabel("Package manager", { exact: true }).selectOption("conda");
  await expect(page).toHaveURL(/check=latest-3\.14-ubuntu-latest/);
  await expect(page.locator(command)).toHaveCount(0);
});

test("a conda check link does not remember conda for other platforms", async ({ page }) => {
  await page.goto(`?platform=linux&check=${condaCheck}`);
  await expect(page.getByLabel("Package manager", { exact: true })).toHaveValue("conda");
  await page.getByLabel("Operating system", { exact: true }).selectOption("macos");
  await expect(page).toHaveURL(/platform=macos/);
  await expect(page.locator(`${command} pre`)).toContainText("/compat/latest-3.12-macos");
  await expect(page.getByLabel("Package manager", { exact: true })).not.toHaveValue("conda");
  expect(await page.evaluate(() => localStorage.getItem("bwbench.manager"))).not.toBe("conda");
});

test("an unknown check id keeps the saved manager's cross-check set", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("bwbench.manager", "conda"));
  await page.goto("?platform=linux&check=no-such-check");
  await expect(page.locator(`${command} pre`)).toContainText("/compat/conda-forge-");
  await expect(page.getByLabel("Package manager", { exact: true })).toHaveValue("conda");
});

test("the OS select keeps focus when the new platform has no passing set", async ({ page }) => {
  const data: Guidance = JSON.parse(
    await readFile(new URL("../test/fixtures/real/guidance.json", import.meta.url), "utf8"),
  );
  data.checks = data.checks.filter((c) => c.platform !== "macos");
  for (const p of data.platforms) if (p.id === "macos") delete p.defaultCheck;
  await page.route("**/data/guidance.json", (route) => route.fulfill({ json: data }));
  await page.goto("?platform=linux");
  const os = page.getByLabel("Operating system", { exact: true });
  await os.focus();
  await os.selectOption("macos");
  await expect(page.locator(".no-saved")).toContainText("No passing set is published for macOS");
  await expect(page.getByLabel("Operating system", { exact: true })).toBeFocused();
});

test("a failed test-suite result beside the command says what it covers", async ({ page }) => {
  await page.goto("?platform=linux");
  await expect(page.locator(".result-line")).toContainText("Failed Upstream test suites · Python 3.12");
  await expect(page.locator(".install-set")).toContainText(
    "Upstream test suites did not pass on the latest releases. They run each package's own tests, which cover more than these calculation checks.",
  );
  await expect(page.locator(".install-set")).toContainText("it is the last set that passed the Latest releases check");
});
