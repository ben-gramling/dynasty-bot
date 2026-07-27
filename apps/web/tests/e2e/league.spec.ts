import { expect, test } from "@playwright/test";

/**
 * League tab against the live seeded DB (scoring v3): the strength map has
 * all 12 teams, my team is anchored with the six-pointed star, the market
 * group shows posture / holes / pick inventory / FAAB (no ω, no cuts), and
 * the chart section is up.
 */

test.beforeEach(async ({ page }) => {
  await page.goto("/league");
});

test("strength map has 12 team rows", async ({ page }) => {
  await expect(page.getByRole("heading", { name: "Strength map" })).toBeVisible();
  const rows = page.locator('section[aria-labelledby="strength-map"] tbody tr');
  await expect(rows).toHaveCount(12);
});

test("my team is highlighted with the star", async ({ page }) => {
  // The my-team row is the one that carries the six-pointed star marker.
  const star = page
    .locator('section[aria-labelledby="strength-map"]')
    .getByRole("img", { name: "Your team" });
  await expect(star).toBeVisible();
  const myRow = page.locator('section[aria-labelledby="strength-map"] tbody tr', {
    // `has:` inner locators resolve relative to the row — keep it unprefixed.
    has: page.getByRole("img", { name: "Your team" }),
  });
  await expect(myRow).toHaveCount(1);
  // Highlight is a distinct row background, not just the star.
  const bg = await myRow.evaluate((el) => getComputedStyle(el).backgroundColor);
  expect(bg).not.toBe("rgba(0, 0, 0, 0)");
});

test("market group shows posture and FAAB, not ω", async ({ page }) => {
  const section = page.locator('section[aria-labelledby="strength-map"]');
  await expect(section.locator("th", { hasText: "Posture" })).toBeVisible();
  await expect(section.locator("th", { hasText: "Holes" })).toBeVisible();
  await expect(section.locator("th", { hasText: "FAAB" })).toBeVisible();
  // v1 columns are gone.
  await expect(section.locator("th", { hasText: "ω" })).toHaveCount(0);
  await expect(section.locator("th", { hasText: "Cuts" })).toHaveCount(0);
  // Every posture cell reads as an observed label.
  const firstPosture = section
    .locator("tbody tr")
    .first()
    .locator("td")
    .filter({ hasText: /^(buyer|seller|neutral)/ });
  await expect(firstPosture.first()).toBeVisible();
});

test("position chart renders bars and keeps a table view", async ({ page }) => {
  await expect(page.getByRole("heading", { name: "Position by position" })).toBeVisible();
  const section = page.locator('section[aria-labelledby="position-chart"]');
  expect(await section.locator("svg, [role='img']").count()).toBeGreaterThan(0);
  // Chart rules: a table view always exists somewhere on the tab.
  expect(await page.locator("table").count()).toBeGreaterThan(0);
});
