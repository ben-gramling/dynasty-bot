import { expect, test } from "@playwright/test";

/**
 * Trades tab against the live seeded DB: ranked offers render as cards,
 * every opponent gets a block, and both sides of a deal carry the
 * decomposition sentence.
 */

test.beforeEach(async ({ page }) => {
  await page.goto("/trades");
});

test("best offers render as real trade cards", async ({ page }) => {
  await expect(page.getByRole("heading", { name: "Best offers" })).toBeVisible();
  const cards = page.locator('section[aria-labelledby="best-offers"] article');
  expect(await cards.count()).toBeGreaterThan(0);
  // Two-sided ethic: You send / You get on every card.
  await expect(cards.first().getByText("You send")).toBeVisible();
  await expect(cards.first().getByText("You get")).toBeVisible();
});

test("all 11 opponents get a block", async ({ page }) => {
  await expect(page.getByRole("heading", { name: "Opponent by opponent" })).toBeVisible();
  const blocks = page.locator('section[aria-labelledby="by-opponent"] > div > article');
  expect(await blocks.count()).toBe(11);
});

test("a trade decomposition expands on click", async ({ page }) => {
  // Pin the first closed decomposition by index — a :not([open]) locator
  // would re-resolve to the next closed one after the click.
  const decomps = page.locator("details.decomp");
  const idx = await decomps.evaluateAll((els) =>
    els.findIndex((el) => !el.hasAttribute("open")),
  );
  expect(idx).toBeGreaterThanOrEqual(0);
  const decomp = decomps.nth(idx);
  await expect(decomp).toBeVisible();
  await decomp.locator("summary").click();
  await expect(decomp).toHaveJSProperty("open", true);
  await expect(decomp.locator(".decomp-audit")).toBeVisible();
});
