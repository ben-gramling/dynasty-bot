import { expect, test } from "@playwright/test";

/**
 * Trades tab against the live seeded DB (scoring v3.2, pairs-only page): the
 * count-neutral hedged-pair section renders first (embedded buy+sell leg
 * cards, combined ΔW, the "0 players / 0 picks net" badge) — and NOTHING that
 * isn't a trade with an associated hedge: no unpaired-legs section, no watch
 * list, no standalone cards. Market map still points into the League tab.
 */

test.beforeEach(async ({ page }) => {
  await page.goto("/trades");
});

test("only hedged pairs render — no unpaired legs, no watch list", async ({
  page,
}) => {
  await expect(
    page.getByRole("heading", { name: "Recommended trades" }),
  ).toBeVisible();
  const sections = page.locator("section[aria-labelledby]");
  await expect(sections.first()).toHaveAttribute("aria-labelledby", "pairs");
  // The pruned sections are gone entirely.
  expect(await page.locator('section[aria-labelledby="sell-legs"]').count()).toBe(0);
  expect(await page.locator('section[aria-labelledby="watch"]').count()).toBe(0);
  await expect(
    page.getByRole("heading", { name: /Unpaired legs/ }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("heading", { name: /Watch — buys with no clean exit/ }),
  ).toHaveCount(0);
  // Exactly two content sections: pairs + market map.
  expect(await sections.count()).toBe(2);
});

test("pairs render fully or the empty state is honest", async ({ page }) => {
  const section = page.locator('section[aria-labelledby="pairs"]');
  const pairCards = section.locator("article", { hasText: "pair ΔW" });
  if ((await pairCards.count()) === 0) {
    // No count-neutral pair in today's data — §5 v3.2 strict: scarcity is
    // correct, never relaxed; and no other trade card may leak onto the page.
    await expect(
      section.getByText(/No count-neutral pair clears today/),
    ).toBeVisible();
    expect(await page.getByText("You send").count()).toBe(0);
    return;
  }
  const first = pairCards.first();
  await expect(first.getByText("pair ΔW")).toBeVisible();
  await expect(
    first.getByText("0 players / 0 picks net", { exact: true }),
  ).toBeVisible();
  await expect(first.getByText("buy leg", { exact: true })).toBeVisible();
  await expect(first.getByText("sell leg", { exact: true })).toBeVisible();
  // Each embedded leg is a full card: two-sided ethic + gate strip + ceiling.
  expect(await first.getByText("You send").count()).toBe(2);
  expect(await first.getByText("You get").count()).toBe(2);
  expect(await first.getByText("PASS", { exact: true }).count()).toBe(2);
  await expect(
    first.getByText(/Band ceiling for this package/).first(),
  ).toBeVisible();
});

test("market map links into the League tab", async ({ page }) => {
  await expect(page.getByRole("heading", { name: "Market map" })).toBeVisible();
  const link = page
    .locator('section[aria-labelledby="market-map"]')
    .getByRole("link", { name: /League tab/ });
  await expect(link).toBeVisible();
  await expect(link).toHaveAttribute("href", "/league");
});
