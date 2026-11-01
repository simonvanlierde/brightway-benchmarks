import { expect, test } from "@playwright/test";

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
