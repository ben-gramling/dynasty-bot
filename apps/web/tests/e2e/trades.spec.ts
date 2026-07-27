import { expect, test } from "@playwright/test";

/**
 * Trades tab against the live seeded DB (scoring v3.1): the hedged-pair
 * section renders FIRST (embedded buy+sell leg cards with the combined ΔW),
 * the labeled sell-side section follows with no standalone buy card anywhere,
 * and the market map points into the League tab.
 */

test.beforeEach(async ({ page }) => {
  await page.goto("/trades");
});

test("recommended trades (hedged pairs) render first with combined ΔW", async ({
  page,
}) => {
  await expect(
    page.getByRole("heading", { name: "Recommended trades" }),
  ).toBeVisible();
  // Pair-first board: the pairs section precedes the sell-side section.
  const sections = page.locator("section[aria-labelledby]");
  await expect(sections.first()).toHaveAttribute("aria-labelledby", "pairs");
  const section = page.locator('section[aria-labelledby="pairs"]');
  const pairCards = section.locator("article", { hasText: "pair ΔW" });
  if ((await pairCards.count()) === 0) {
    // No pairs in today's data — the section must say so honestly.
    await expect(section.getByText(/No hedged pair clears today/)).toBeVisible();
    return;
  }
  const first = pairCards.first();
  // Combined ΔW chip, net-roster line, and BOTH embedded leg cards.
  await expect(first.getByText("pair ΔW")).toBeVisible();
  await expect(first.getByText(/net roster/)).toBeVisible();
  await expect(first.getByText("buy leg", { exact: true })).toBeVisible();
  await expect(first.getByText("sell leg", { exact: true })).toBeVisible();
  // Each embedded leg is a full card: two-sided ethic + gate strip.
  expect(await first.getByText("You send").count()).toBe(2);
  expect(await first.getByText("You get").count()).toBe(2);
  expect(await first.getByText("PASS", { exact: true }).count()).toBe(2);
});

test("leg cards carry the v3.1 band ceiling and posture/sequencing notes", async ({
  page,
}) => {
  const anyCard = page
    .locator("article.card", { hasText: "You send" })
    .first();
  await expect(anyCard.getByText(/Band ceiling for this package/)).toBeVisible();
  await expect(anyCard.getByText(/negotiating room above the proposal/)).toBeVisible();
  await expect(anyCard.getByText(/Shape: (players|picks|mixed) →/)).toBeVisible();
  await expect(anyCard.getByText(/Sequencing:/)).toBeVisible();
});

test("sell-side section is labeled and carries no standalone buy card", async ({
  page,
}) => {
  await expect(
    page.getByRole("heading", { name: "Sell-side legs (no hedge needed)" }),
  ).toBeVisible();
  const section = page.locator('section[aria-labelledby="sell-legs"]');
  // Never a standalone buy: no buy-leg badge outside the pairs section.
  expect(await section.getByText("buy leg", { exact: true }).count()).toBe(0);
  const cards = section.locator("article", { hasText: "You send" });
  if ((await cards.count()) === 0) {
    await expect(section.getByText(/No standalone sell clears today/)).toBeVisible();
    return;
  }
  const first = cards.first();
  await expect(first.getByText("ΔW you")).toBeVisible();
  const themLine = first.locator('[title*="zero-sum"]');
  await expect(themLine).toBeVisible();
  await expect(themLine).toHaveText(/them/);
  await expect(first.getByText(/of .*band/)).toBeVisible();
  await expect(first.getByText("PASS", { exact: true })).toBeVisible();
});

test("watch list, when present, blocks buys with one-line blockers", async ({
  page,
}) => {
  const watch = page.locator('section[aria-labelledby="watch"]');
  if ((await watch.count()) === 0) return; // honest absence — nothing to watch
  await expect(
    watch.getByRole("heading", { name: /Watch — buys with no clean exit/ }),
  ).toBeVisible();
  await expect(watch.getByText(/no clean exit/).first()).toBeVisible();
  // Watch entries are notes, not proposal cards — no gate strip inside.
  expect(await watch.getByText("PASS", { exact: true }).count()).toBe(0);
});

test("market map links into the League tab", async ({ page }) => {
  await expect(page.getByRole("heading", { name: "Market map" })).toBeVisible();
  const link = page
    .locator('section[aria-labelledby="market-map"]')
    .getByRole("link", { name: /League tab/ });
  await expect(link).toBeVisible();
  await expect(link).toHaveAttribute("href", "/league");
});
