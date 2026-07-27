import { expect, test } from "@playwright/test";

/**
 * Trades tab against the live seeded DB (scoring v3.3, dial-filtered pairs
 * page): the target-return dial filters the stored count-neutral pairs, the
 * header count line comes from the engine's honest counts_by_threshold
 * (saturated counters render "≥ N"), truncation is disclosed, and NOTHING
 * that isn't a pair renders: no unpaired-legs section, no watch list, no
 * standalone cards. Market map still points into the League tab.
 */

test.beforeEach(async ({ page }) => {
  await page.goto("/trades");
});

test("only pairs render — no unpaired legs, no watch list", async ({
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

test("the return dial is present, defaults to 5%, and drives the count line", async ({
  page,
}) => {
  const dial = page.getByRole("group", { name: "Target return" });
  await expect(dial).toBeVisible();
  for (const label of ["1%", "2.5%", "5%", "10%", "20%"]) {
    await expect(dial.getByRole("button", { name: label, exact: true })).toBeVisible();
  }
  await expect(dial.getByRole("button", { name: "5%", exact: true })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  // The count line reads "N pairs ≥ target (of M ≥ 1%)" — honest counts,
  // "≥ N" when the engine's counter saturated.
  const countLine = page.getByText(/pairs? ≥ 5% \(of .* ≥ 1%\)/);
  await expect(countLine).toBeVisible();
  const before = await countLine.textContent();
  await dial.getByRole("button", { name: "20%", exact: true }).click();
  await expect(dial.getByRole("button", { name: "20%", exact: true })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  const after = page.getByText(/pairs? ≥ 20% \(of .* ≥ 1%\)/);
  await expect(after).toBeVisible();
  expect(await after.textContent()).not.toBe(before);
});

test("pairs render fully at every target or the empty state is honest", async ({
  page,
}) => {
  const section = page.locator('section[aria-labelledby="pairs"]');
  const dial = page.getByRole("group", { name: "Target return" });
  for (const label of ["1%", "5%", "20%"]) {
    await dial.getByRole("button", { name: label, exact: true }).click();
    const pairCards = section.locator("article", { hasText: "pair ΔW" });
    const n = await pairCards.count();
    if (n === 0) {
      // Empty at this target: the message must name a lower preset that still
      // clears ("No pairs clear 10% today — 12 clear 2.5%") or say none do.
      await expect(
        section.getByText(
          new RegExp(
            `No pairs clear ${label.replace("%", "")}% today — (.*clear \\d+(\\.\\d+)?%|and none clear any lower preset)`,
          ),
        ),
      ).toBeVisible();
      expect(await section.getByText("You send").count()).toBe(0);
      continue;
    }
    // Rendered list is capped at 50, with the cap disclosed.
    expect(n).toBeLessThanOrEqual(50);
    if (n === 50) {
      await expect(section.getByText(/Showing the top 50 of \d+ stored/)).toBeVisible();
    }
    const first = pairCards.first();
    await expect(first.getByText("pair ΔW")).toBeVisible();
    await expect(first.getByText(/% return/)).toBeVisible();
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
  }
});

test("truncation is disclosed honestly when the storage cap binds", async ({
  page,
}) => {
  // Live-data dependent: when the engine truncated, the disclosure names both
  // the stored cap and the (possibly floor-form) total; when it did not, no
  // storage-cap line renders at all.
  const note = page.getByText(/Storage cap: the top [\d,]+ pairs by return/);
  if ((await note.count()) > 0) {
    await expect(note).toContainText(/of (at least )?[\d,]+ clearing/);
  }
});

test("market map links into the League tab", async ({ page }) => {
  await expect(page.getByRole("heading", { name: "Market map" })).toBeVisible();
  const link = page
    .locator('section[aria-labelledby="market-map"]')
    .getByRole("link", { name: /League tab/ });
  await expect(link).toBeVisible();
  await expect(link).toHaveAttribute("href", "/league");
});
