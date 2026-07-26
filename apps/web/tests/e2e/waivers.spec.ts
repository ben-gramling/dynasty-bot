import { expect, test } from "@playwright/test";

/**
 * Waivers tab against the live seeded DB: the board has real rows, the
 * status pill carries a real run time, and the signature decomposition
 * sentence expands to its audit on click.
 */

test.beforeEach(async ({ page }) => {
  await page.goto("/waivers");
});

test("board renders real seeded rows", async ({ page }) => {
  await expect(page.getByRole("heading", { name: "Full board", exact: true })).toBeVisible();
  const rows = page.locator(".wv-row");
  expect(await rows.count()).toBeGreaterThan(0);
  // Every row leads with a KTC value in the data face.
  await expect(rows.first().locator(".num").first()).toBeVisible();
});

test("status pill shows a run time and Refresh exists", async ({ page }) => {
  const pill = page.locator("header .pill");
  await expect(pill).toBeVisible();
  // "Data 2h ago" / "Data just now" — a real collector run, not the empty state.
  await expect(pill).toHaveText(/Data (just now|\d+[mhd] ago)/);
  await expect(page.getByRole("button", { name: "Refresh" })).toBeVisible();
});

test("a decomposition sentence expands to the full audit on click", async ({ page }) => {
  // Pick a closed decomposition (the first claim card ships open by design).
  // Pin it by index — a :not([open]) locator would re-resolve after the click.
  const decomps = page.locator("details.decomp");
  const idx = await decomps.evaluateAll((els) =>
    els.findIndex((el) => !el.hasAttribute("open")),
  );
  expect(idx).toBeGreaterThanOrEqual(0);
  const closed = decomps.nth(idx);
  await expect(closed).toBeVisible();
  const audit = closed.locator(".decomp-audit");
  await expect(audit).toBeHidden();
  await closed.locator("summary").click();
  await expect(closed).toHaveJSProperty("open", true);
  await expect(audit).toBeVisible();
  // The audit always closes with the sum line (components must sum, §12).
  await expect(audit.locator("p").last()).toHaveText(/=/);
});

test("board rows expand to the plan line and decomposition", async ({ page }) => {
  const row = page.locator(".wv-row").first();
  await row.locator("summary").first().click();
  await expect(row.locator(".wv-plan")).toBeVisible();
  await expect(row.locator(".decomp")).toBeVisible();
});

test("position filter pills exist with real counts", async ({ page }) => {
  const all = page.locator(".wv-filter label", { hasText: "All" });
  await expect(all).toBeVisible();
  const count = Number(await all.locator(".num").innerText());
  expect(count).toBeGreaterThan(0);
});
