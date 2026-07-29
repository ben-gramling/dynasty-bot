import { expect, test } from "@playwright/test";

/**
 * Trades tab against the live seeded DB (scoring v4, two-dial pairs page): a
 * TOTAL-return floor (v4: floor-based — the guaranteed gain min(ΔS, ΔF) over
 * face sent) and a PER-LEG market-return cap filter the stored pairs —
 * independent dimensions, no combination disabled, the list always in
 * maximin order (guaranteed return desc, ceiling tie-break). The inventory
 * line comes from the engine's honest per-bucket `bands` grid (saturated
 * counts render "≥ N" — verified floors, never estimates), cards render BOTH
 * sides' own coordinates ("starters +X · face +Y" — ΔF zero-sum per leg, ΔS
 * per side) with the guaranteed interval and each leg's market return, and
 * NOTHING that isn't a pair renders: no unpaired-legs section, no watch
 * list, no standalone cards. Market map still points into the League tab.
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

test("dial controls present with defaults: floor 5%, leg cap No cap", async ({
  page,
}) => {
  const minG = page.getByRole("group", { name: "Minimum return" });
  const capG = page.getByRole("group", { name: "Max per-leg return" });
  await expect(minG).toBeVisible();
  await expect(capG).toBeVisible();
  for (const label of ["1%", "2.5%", "5%", "10%", "20%"]) {
    await expect(minG.getByRole("button", { name: label, exact: true })).toBeVisible();
  }
  for (const label of ["2.5%", "5%", "10%", "20%", "No cap"]) {
    await expect(capG.getByRole("button", { name: label, exact: true })).toBeVisible();
  }
  await expect(minG.getByRole("button", { name: "5%", exact: true })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await expect(
    capG.getByRole("button", { name: "No cap", exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
  // The inventory line reads from the engine's bucket × total-band grid.
  await expect(
    page.getByText(
      /stored shown \(total 5%\+, no leg cap\) · inventory: (≥ )?[\d,]+ legal/,
    ),
  ).toBeVisible();
});

test("the leg cap filters on each leg's market return", async ({ page }) => {
  const capG = page.getByRole("group", { name: "Max per-leg return" });
  const line = page.getByText(/stored shown \(total .*\) · inventory:/);
  const before = await line.textContent();
  await capG.getByRole("button", { name: "10%", exact: true }).click();
  await expect(
    capG.getByRole("button", { name: "10%", exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
  const after = page.getByText(
    /stored shown \(total 5%\+, legs < 10%\) · inventory:/,
  );
  await expect(after).toBeVisible();
  expect(await after.textContent()).not.toBe(before);
  const section = page.locator('section[aria-labelledby="pairs"]');
  // Top-level pair cards only: anchor on the pair heading (embedded leg
  // articles carry their own coordinate lines).
  const cards = section
    .locator("article")
    .filter({ has: page.getByRole("heading", { name: "Buy + sell" }) });
  const n = await cards.count();
  for (let i = 0; i < Math.min(n, 5); i++) {
    const card = cards.nth(i);
    // v3.4.1: EVERY leg's market return respects the cap (rendered at 1 dp,
    // so allow the rounding window), while the TOTAL return may exceed it —
    // and the sort stays total-desc regardless of the cap.
    const legTxt = await card.getByText(/legs: buy /).first().textContent();
    const m = /legs: buy ([+−][\d.,]+)% · sell ([+−][\d.,]+)% market/.exec(
      legTxt ?? "",
    );
    expect(m).not.toBeNull();
    const legs = [m![1], m![2]].map((s) =>
      parseFloat(s.replace("−", "-").replace(",", "")),
    );
    expect(Math.max(...legs)).toBeLessThan(10.05);
  }
});

test("floor 5% with leg cap 2.5% is a valid query — no combination disables", async ({
  page,
}) => {
  // v3.4.1: the dials are independent dimensions. A high total floor under a
  // low per-leg cap is the flagship query (legs look nearly even, the pair
  // total is large) — the v3.3.1 min<max coupling is retired.
  const minG = page.getByRole("group", { name: "Minimum return" });
  const capG = page.getByRole("group", { name: "Max per-leg return" });
  for (const label of ["1%", "2.5%", "5%", "10%", "20%"]) {
    await expect(minG.getByRole("button", { name: label, exact: true })).toBeEnabled();
  }
  for (const label of ["2.5%", "5%", "10%", "20%", "No cap"]) {
    await expect(capG.getByRole("button", { name: label, exact: true })).toBeEnabled();
  }
  await capG.getByRole("button", { name: "2.5%", exact: true }).click();
  await expect(
    capG.getByRole("button", { name: "2.5%", exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
  await expect(
    minG.getByRole("button", { name: "5%", exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
  await expect(
    page.getByText(/stored shown \(total 5%\+, legs < 2.5%\) · inventory:/),
  ).toBeVisible();
  // every button stays enabled even with the tightest cap active
  for (const label of ["10%", "20%"]) {
    await expect(minG.getByRole("button", { name: label, exact: true })).toBeEnabled();
  }
});

test("pairs render fully behind every dial combo or the empty state is honest", async ({
  page,
}) => {
  const section = page.locator('section[aria-labelledby="pairs"]');
  const minG = page.getByRole("group", { name: "Minimum return" });
  const capG = page.getByRole("group", { name: "Max per-leg return" });
  const combos: [string, string][] = [
    ["1%", "2.5%"],
    ["5%", "2.5%"], // v3.4.1 flagship: high total floor UNDER a low leg cap
    ["20%", "No cap"],
  ];
  for (const [minL, capL] of combos) {
    // No coupling between the dials (v3.4.1) — click order is free.
    await minG.getByRole("button", { name: minL, exact: true }).click();
    await capG.getByRole("button", { name: capL, exact: true }).click();
    const pairCards = section
      .locator("article")
      .filter({ has: page.getByRole("heading", { name: "Buy + sell" }) });
    const n = await pairCards.count();
    if (n === 0) {
      // Empty filter: the message must quantify what each loosening exposes,
      // or say nothing survives either dial alone.
      await expect(
        section.getByText(
          /No stored pairs with total .* today — (removing the leg cap exposes [\d,]+ stored, dropping the floor to [\d.]+% exposes [\d,]+|and no stored pair survives either dial alone)/,
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
    // v4: the pair metric chip is the guaranteed floor ("guaranteed ΔW");
    // the % return is floor-based.
    await expect(first.getByText("guaranteed ΔW", { exact: true })).toBeVisible();
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
    // v4: each leg shows the counterparty's OWN coordinates — ΔF negates
    // across sides (face conserves), ΔS never forced to (per side).
    expect(await first.getByText(/them: starters /).count()).toBe(2);
    // The coordinate lines are optional in the doc shape (boards written
    // before v4 carry the retired ledger split), so assert their SHAPE only
    // when the seeded DB supplies them: present on a leg ⇒ present as
    // you/them on both legs plus the pair's combined line (2×2 + 1 = 5).
    const splits = await first
      .getByText(/starters [+−]\S* · face [+−]/)
      .count();
    if (splits > 0) expect(splits).toBe(5);
    await expect(
      first.getByText(/Band ceiling for this package/).first(),
    ).toBeVisible();
  }
});

test("bucket inventory floors are disclosed honestly", async ({ page }) => {
  // Live-data dependent: when any selected bucket is saturated, the inventory
  // renders "≥ N" and the verified-floor note appears; when none is, neither
  // does. (Under v3.4 every count is a floor, so both normally show.)
  const line = page.getByText(/inventory: (≥ )?[\d,]+ legal/);
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
