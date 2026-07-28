import { expect, test } from "@playwright/test";

/**
 * Trades tab against the live seeded DB (scoring v3.4, range-filtered pairs
 * page): min/max target-return range controls filter the stratified stored
 * pairs, the inventory line comes from the engine's honest per-band `bands`
 * counts (saturated bands render "≥ N" — verified floors, never estimates),
 * invalid min/max combos are disabled, cards render BOTH sides' own wealth
 * ledgers (v3.4 ΔW is per side, never ±zero-sum) with the starters/picks
 * split, and NOTHING that isn't a pair renders: no unpaired-legs section, no
 * watch list, no standalone cards. Market map still points into the League tab.
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

test("range controls present with defaults: min 5%, max No cap", async ({
  page,
}) => {
  const minG = page.getByRole("group", { name: "Minimum return" });
  const maxG = page.getByRole("group", { name: "Maximum return" });
  await expect(minG).toBeVisible();
  await expect(maxG).toBeVisible();
  for (const label of ["1%", "2.5%", "5%", "10%", "20%"]) {
    await expect(minG.getByRole("button", { name: label, exact: true })).toBeVisible();
  }
  for (const label of ["2.5%", "5%", "10%", "20%", "No cap"]) {
    await expect(maxG.getByRole("button", { name: label, exact: true })).toBeVisible();
  }
  await expect(minG.getByRole("button", { name: "5%", exact: true })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await expect(
    maxG.getByRole("button", { name: "No cap", exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
  // The inventory line reads from the engine's per-band counts.
  await expect(
    page.getByText(/shown in 5%\+ · band inventory: [\d,]+ stored of (≥ )?[\d,]+ legal/),
  ).toBeVisible();
});

test("switching max changes the rendered set and the count line", async ({
  page,
}) => {
  const maxG = page.getByRole("group", { name: "Maximum return" });
  const line = page.getByText(/shown in .* · band inventory:/);
  const before = await line.textContent();
  await maxG.getByRole("button", { name: "10%", exact: true }).click();
  await expect(
    maxG.getByRole("button", { name: "10%", exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
  const after = page.getByText(/shown in 5–10% · band inventory:/);
  await expect(after).toBeVisible();
  expect(await after.textContent()).not.toBe(before);
  // Every rendered pair's return respects the cap.
  const section = page.locator('section[aria-labelledby="pairs"]');
  const returns = section.locator("article", { hasText: "pair ΔW" });
  const n = await returns.count();
  for (let i = 0; i < Math.min(n, 5); i++) {
    const txt = await returns.nth(i).getByText(/% return/).first().textContent();
    const val = parseFloat((txt ?? "").replace("% return", "").replace("+", ""));
    // cards render the return at 1 dp, so a 9.98% pair shows "10.0%" —
    // assert with rendering-rounding tolerance
    expect(val).toBeGreaterThanOrEqual(4.95);
    expect(val).toBeLessThan(10.05);
  }
});

test("invalid min/max combos are prevented", async ({ page }) => {
  const minG = page.getByRole("group", { name: "Minimum return" });
  const maxG = page.getByRole("group", { name: "Maximum return" });
  // Default min 5: max 2.5 and max 5 must be disabled.
  await expect(maxG.getByRole("button", { name: "2.5%", exact: true })).toBeDisabled();
  await expect(maxG.getByRole("button", { name: "5%", exact: true })).toBeDisabled();
  await expect(maxG.getByRole("button", { name: "10%", exact: true })).toBeEnabled();
  // Cap at 10: min 10 and 20 must be disabled; drop min to 1 and 2.5 stays open.
  await maxG.getByRole("button", { name: "10%", exact: true }).click();
  await expect(minG.getByRole("button", { name: "10%", exact: true })).toBeDisabled();
  await expect(minG.getByRole("button", { name: "20%", exact: true })).toBeDisabled();
  await expect(minG.getByRole("button", { name: "1%", exact: true })).toBeEnabled();
  await minG.getByRole("button", { name: "1%", exact: true }).click();
  await expect(maxG.getByRole("button", { name: "2.5%", exact: true })).toBeEnabled();
});

test("pairs render fully in every range or the empty state is honest", async ({
  page,
}) => {
  const section = page.locator('section[aria-labelledby="pairs"]');
  const minG = page.getByRole("group", { name: "Minimum return" });
  const maxG = page.getByRole("group", { name: "Maximum return" });
  const ranges: [string, string][] = [
    ["1%", "2.5%"],
    ["5%", "10%"],
    ["20%", "No cap"],
  ];
  for (const [minL, maxL] of ranges) {
    // Order avoids transient invalid states: open the cap, set min, then cap.
    await maxG.getByRole("button", { name: "No cap", exact: true }).click();
    await minG.getByRole("button", { name: minL, exact: true }).click();
    await maxG.getByRole("button", { name: maxL, exact: true }).click();
    const pairCards = section.locator("article", { hasText: "pair ΔW" });
    const n = await pairCards.count();
    if (n === 0) {
      // Empty range: the message must name a band that still has inventory
      // ("the 10–20% band holds 100") or say no band holds any.
      await expect(
        section.getByText(
          /No stored pairs in .* today — (the [\d.]+(–[\d.]+)?%\+? band holds [\d,]+|and no band holds any stored pairs)/,
        ),
      ).toBeVisible();
      expect(await section.getByText("You send").count()).toBe(0);
      continue;
    }
    // Rendered list is capped at 50, with the cap disclosed.
    expect(n).toBeLessThanOrEqual(50);
    if (n === 50) {
      await expect(
        section.getByText(/Showing the top 50 of \d+ stored/),
      ).toBeVisible();
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
    // v3.4: each leg shows the counterparty's OWN ledger delta — never a
    // ±zero-sum negation of ours.
    expect(await first.getByText(/their ledger/).count()).toBe(2);
    // The starters/picks split is optional in the doc shape (boards written
    // before v3.4 carry none), so assert its SHAPE only when the seeded DB
    // supplies it: present on a leg ⇒ present on both legs and on the pair.
    const splits = await first
      .getByText(/starters [+−]\S* · picks [+−]/)
      .count();
    if (splits > 0) expect(splits).toBe(3);
    await expect(
      first.getByText(/Band ceiling for this package/).first(),
    ).toBeVisible();
  }
});

test("band inventory floors are disclosed honestly", async ({ page }) => {
  // Live-data dependent: when any band in the selected range is saturated,
  // the inventory renders "≥ N" and the verified-floor note appears; when
  // none is, neither does.
  const line = page.getByText(/band inventory: [\d,]+ stored of (≥ )?[\d,]+ legal/);
  await expect(line).toBeVisible();
  const text = (await line.textContent()) ?? "";
  const note = page.getByText(/Inventory marked ≥ is a verified floor/);
  if (text.includes("≥")) {
    await expect(note).toBeVisible();
  } else {
    expect(await note.count()).toBe(0);
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
