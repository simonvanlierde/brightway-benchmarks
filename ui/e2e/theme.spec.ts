import { expect, test } from "@playwright/test";

test("the system theme follows preference changes until a visitor chooses a theme", async ({ page }) => {
  await page.emulateMedia({ colorScheme: "dark" });
  await page.goto("/");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page.emulateMedia({ colorScheme: "light" });
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  await page.locator("[data-theme-toggle]").click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page.emulateMedia({ colorScheme: "dark" });
  await page.emulateMedia({ colorScheme: "light" });
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await expect(page.locator("[data-theme-toggle]")).toHaveAccessibleName("Switch to light theme");
});

test("About uses the same saved theme and can change it without hydrating an app", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("bwbench.theme", "dark"));
  await page.goto("/about/");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page.getByRole("button", { name: "Switch to light theme" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  expect(await page.evaluate(() => localStorage.getItem("bwbench.theme"))).toBe("light");
  await expect(page.locator("astro-island")).toHaveCount(0);
});

test("theme switching works when local storage is blocked", async ({ page }) => {
  await page.addInitScript(() => {
    Object.defineProperty(window, "localStorage", {
      get: () => {
        throw new Error("Storage blocked");
      },
    });
  });
  await page.emulateMedia({ colorScheme: "light" });
  await page.goto("/about/");
  await page.getByRole("button", { name: "Switch to dark theme" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page.getByRole("button", { name: "Switch to light theme" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
});

test("changing the theme redraws chart colors", async ({ page }) => {
  await page.emulateMedia({ colorScheme: "light" });
  await page.goto("?bench=bw2calc-bench-import-timeraw-import-bw2calc-c078f5d2c0be");
  const chart = page.locator(".chart svg");
  await expect(chart).toBeVisible();
  const light = await chart.evaluate((svg) => (svg as SVGElement).style.color);
  expect(light).not.toBe("");
  await expect(page.locator('[data-theme-icon="moon"]')).toBeVisible();
  await expect(page.locator('[data-theme-icon="sun"]')).toBeHidden();
  await page.getByRole("button", { name: "Switch to dark theme" }).click();
  await expect.poll(() => chart.evaluate((svg) => (svg as SVGElement).style.color)).not.toBe(light);
  await expect(page.locator('[data-theme-icon="sun"]')).toBeVisible();
  await expect(page.locator('[data-theme-icon="moon"]')).toBeHidden();
});
