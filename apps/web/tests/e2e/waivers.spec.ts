import { expect, test } from "@playwright/test";

/**
 * Waivers tab against the live seeded DB (scoring v3): the board has real
 * rows ranked by claim score, rows expand to the plan line, the drop list
 * is the ascending housekeeping list, and the status pill carries a real
 * run time.
 */

test.beforeEach(async ({ page }) => {
  await page.goto("/waivers");
});

test("board renders real seeded rows with the claim column", async ({ page }) => {
  await expect(
    page.getByRole("heading", { name: "Full board", exact: true }),
  ).toBeVisible();
  const rows = page.locator(".wv-row");
  expect(await rows.count()).toBeGreaterThan(0);
  // Every row leads with a KTC value in the data face.
  await expect(rows.first().locator(".num").first()).toBeVisible();
  // v3 board header: Claim replaces NetClaim; no Net/Raw split.
  const head = page.locator(".wv-head").first();
  await expect(head.getByText("Claim", { exact: true })).toBeVisible();
  await expect(head.getByText("Net", { exact: true })).toHaveCount(0);
});

test("status pill shows a run time and Refresh exists", async ({ page }) => {
  const pill = page.locator("header .pill");
  await expect(pill).toBeVisible();
  // "Data 2h ago" / "Data just now" — a real collector run, not the empty state.
  await expect(pill).toHaveText(/Data (just now|\d+[mhd] ago)/);
  await expect(page.getByRole("button", { name: "Refresh" })).toBeVisible();
});

test("board rows expand to the plan line", async ({ page }) => {
  const row = page.locator("details.wv-row").first();
  await row.locator("summary").first().click();
  await expect(row).toHaveJSProperty("open", true);
  const plan = row.locator(".wv-plan");
  await expect(plan).toBeVisible();
  // The plan states the add and the bid in user words.
  await expect(plan).toHaveText(/Add .+ bid \$\d+/);
});

test("drop list is present with the standing drop tagged", async ({ page }) => {
  await expect(page.getByRole("heading", { name: "Drop list" })).toBeVisible();
  await expect(page.getByText("standing drop").first()).toBeVisible();
});

test("position filter pills exist with real counts", async ({ page }) => {
  const all = page.locator(".wv-filter label", { hasText: "All" });
  await expect(all).toBeVisible();
  const count = Number(await all.locator(".num").innerText());
  expect(count).toBeGreaterThan(0);
});
