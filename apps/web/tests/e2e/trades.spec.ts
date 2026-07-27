import { expect, test } from "@playwright/test";

/**
 * Trades tab against the live seeded DB (scoring v3): ranked leg cards carry
 * ΔW both ways and the fairness-gate strip, the roster-neutral pairs section
 * renders (cards when the engine found bundles, honest empty state when not),
 * and the market map points into the League tab.
 */

test.beforeEach(async ({ page }) => {
  await page.goto("/trades");
});

test("best trades render as ranked cards with ΔW and the gate strip", async ({
  page,
}) => {
  await expect(page.getByRole("heading", { name: "Best trades" })).toBeVisible();
  const cards = page.locator('section[aria-labelledby="best-trades"] article');
  expect(await cards.count()).toBeGreaterThan(0);
  const first = cards.first();
  // Two-sided ethic: You send / You get on every card.
  await expect(first.getByText("You send")).toBeVisible();
  await expect(first.getByText("You get")).toBeVisible();
  // Headline ΔW(you) chip plus the honest zero-sum "them" line.
  await expect(first.getByText("ΔW you")).toBeVisible();
  const themLine = first.locator('[title*="zero-sum"]');
  await expect(themLine).toBeVisible();
  await expect(themLine).toHaveText(/them/);
  // The §3 gate strip: band gap, anti-fleece ratio, verdict.
  await expect(first.getByText(/of .*band/)).toBeVisible();
  await expect(first.getByText(/cap/)).toBeVisible();
  await expect(first.getByText("PASS", { exact: true })).toBeVisible();
});

test("cards carry posture shape and sequencing notes", async ({ page }) => {
  const first = page.locator('section[aria-labelledby="best-trades"] article').first();
  await expect(first.getByText(/Shape: (players|picks|mixed) →/)).toBeVisible();
  await expect(first.getByText(/Sequencing:/)).toBeVisible();
});

test("roster-neutral pairs section renders cards or its empty state", async ({
  page,
}) => {
  await expect(
    page.getByRole("heading", { name: "Roster-neutral pairs" }),
  ).toBeVisible();
  const section = page.locator('section[aria-labelledby="pairs"]');
  const pairCards = section.locator("article", { hasText: "pair ΔW" });
  if ((await pairCards.count()) === 0) {
    // No bundles in today's data — the section must say so honestly.
    await expect(section.getByText(/No pairings needed/)).toBeVisible();
    return;
  }
  const first = pairCards.first();
  // A pair names its legs (R-ids) and carries the combined ΔW chip.
  await expect(first.getByText("pair ΔW")).toBeVisible();
  await expect(first.getByText(/net roster/)).toBeVisible();
});

test("market map links into the League tab", async ({ page }) => {
  await expect(page.getByRole("heading", { name: "Market map" })).toBeVisible();
  const link = page
    .locator('section[aria-labelledby="market-map"]')
    .getByRole("link", { name: /League tab/ });
  await expect(link).toBeVisible();
  await expect(link).toHaveAttribute("href", "/league");
});
