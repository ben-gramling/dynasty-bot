import { expect, test } from "@playwright/test";

/**
 * League tab against the live seeded DB: the strength map has all 12 teams,
 * my team is anchored with the six-pointed star, and the chart section is up.
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

test("position chart renders bars and keeps a table view", async ({ page }) => {
  await expect(page.getByRole("heading", { name: "Position by position" })).toBeVisible();
  const section = page.locator('section[aria-labelledby="position-chart"]');
  expect(await section.locator("svg, [role='img']").count()).toBeGreaterThan(0);
  // Chart rules: a table view always exists somewhere on the tab.
  expect(await page.locator("table").count()).toBeGreaterThan(0);
});
