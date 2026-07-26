import { expect, test } from "@playwright/test";

test("/ redirects to /waivers and renders the shell", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveURL(/\/waivers$/);
  await expect(page.getByRole("link", { name: /Chicago Dynasty/i })).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Sections" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Refresh" })).toBeVisible();
});

test("tabs navigate", async ({ page }) => {
  await page.goto("/waivers");
  await page.getByRole("link", { name: "League" }).click();
  await expect(page).toHaveURL(/\/league$/);
  await page.getByRole("link", { name: "Trades" }).click();
  await expect(page).toHaveURL(/\/trades$/);
});
