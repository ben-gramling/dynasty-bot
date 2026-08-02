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
  await page.getByRole("link", { name: "Waivers" }).click();
  await expect(page).toHaveURL(/\/waivers$/);
});

test("the Trades tab is gone — spread-finding is CLI-only (v7.1)", async ({ page }) => {
  await page.goto("/waivers");
  const nav = page.getByRole("navigation", { name: "Sections" });
  await expect(nav.getByRole("link")).toHaveText(["Waivers", "League"]);
  const res = await page.goto("/trades");
  expect(res?.status()).toBe(404);
});
