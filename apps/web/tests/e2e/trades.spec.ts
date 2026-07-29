import { expect, test } from "@playwright/test";

/**
 * Trades tab against the live seeded DB (scoring v5, three-dial pairs page —
 * the finder's sliders over stored inventory, §4a/§5): a δ SELECTOR (robust
 * default + presets 0/0.25/0.5/0.75/1 — return(δ) re-scored client-side from
 * each stored pair's exact coordinates, a labeled preference VIEW), a floor
 * on TOTAL return(δ) (robust = the guaranteed floor min(ΔS, ΔF) over face
 * sent), and a counterparty-favorability FLOOR on the pair's min(f_buy,
 * f_sell) in KTC's own calculator variance units (±5 = their calculator
 * literally says FAIR; replaces the v3.4.1 per-leg market-return cap). No
 * dial combination disables; the list sorts by return(δ) desc, ceiling
 * tie-break. The inventory line comes from the engine's honest favor-bucket ×
 * robust-return `bands` grid (floors render "≥ N" — verified floors, never
 * estimates), cards render BOTH sides' own coordinates ("starters +X · face
 * +Y" — ΔF zero-sum per leg, ΔS per side) with the guaranteed interval, a
 * per-leg favor chip, and the pair favor line, and NOTHING that isn't a pair
 * renders: no unpaired-legs section, no watch list, no standalone cards.
 * Market map still points into the League tab.
 *
 * getByText/getByRole name matching is substring + case-insensitive — every
 * chip-label probe passes exact: true (or an anchored regex).
 */

/** One leg favor chip: FAIR inside the calculator's ±5 window, else named. */
const FAVOR_CHIP = /^(their calculator: FAIR|favors them \+[\d.]+|favors you [\d.]+)$/;

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

test("three dial controls with defaults: robust δ, floor 5%, no favor floor", async ({
  page,
}) => {
  const dG = page.getByRole("group", { name: "Delta view" });
  const minG = page.getByRole("group", { name: "Minimum return" });
  const fG = page.getByRole("group", { name: "Favorability floor" });
  await expect(dG).toBeVisible();
  await expect(minG).toBeVisible();
  await expect(fG).toBeVisible();
  for (const label of ["robust", "0", "0.25", "0.5", "0.75", "1"]) {
    await expect(dG.getByRole("button", { name: label, exact: true })).toBeVisible();
  }
  for (const label of ["1%", "2.5%", "5%", "10%", "20%"]) {
    await expect(minG.getByRole("button", { name: label, exact: true })).toBeVisible();
  }
  for (const label of ["−10", "−5", "0", "+2.5", "+5", "No floor"]) {
    await expect(fG.getByRole("button", { name: label, exact: true })).toBeVisible();
  }
  await expect(
    dG.getByRole("button", { name: "robust", exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
  await expect(minG.getByRole("button", { name: "5%", exact: true })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await expect(
    fG.getByRole("button", { name: "No floor", exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
  // The inventory line reads from the engine's favor-bucket × robust-return
  // grid; robust default sorts by the guaranteed return.
  await expect(
    page.getByText(
      /stored shown \(total 5%\+ robust, no favor floor\) · inventory: (≥ )?[\d,]+ legal · sorted by guaranteed return/,
    ),
  ).toBeVisible();
  // No preference view is active by default.
  expect(await page.getByText(/preference view at δ=/).count()).toBe(0);
});

test("the favor floor filters on the pair's least-happy counterparty", async ({
  page,
}) => {
  const fG = page.getByRole("group", { name: "Favorability floor" });
  await fG.getByRole("button", { name: "−5", exact: true }).click();
  await expect(
    fG.getByRole("button", { name: "−5", exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
  await expect(
    page.getByText(
      /stored shown \(total 5%\+ robust, favor ≥ −5\) · inventory:/,
    ),
  ).toBeVisible();
  const section = page.locator('section[aria-labelledby="pairs"]');
  const cards = section
    .locator("article")
    .filter({ has: page.getByRole("heading", { name: "Buy + sell" }) });
  const n = await cards.count();
  if (n === 0) {
    // Honest empty state: quantified loosenings, or nothing survives alone.
    await expect(
      section.getByText(
        /No stored pairs with total 5%\+ robust, favor ≥ −5 today — (removing the favor floor exposes [\d,]+ stored, dropping the return floor to [\d.]+% exposes [\d,]+|and no stored pair survives either dial alone)/,
      ),
    ).toBeVisible();
    return;
  }
  for (let i = 0; i < Math.min(n, 5); i++) {
    // v5: every rendered pair's favor min (the least-happy counterparty, in
    // KTC's own variance units) respects the floor — rendered at 1 dp, so
    // allow the rounding window.
    const favTxt = await cards.nth(i).getByText(/favor: buy /).first().textContent();
    const m = / min ([+−][\d.,]+)$/.exec(favTxt ?? "");
    expect(m).not.toBeNull();
    const v = parseFloat(m![1].replace("−", "-").replace(",", ""));
    expect(v).toBeGreaterThanOrEqual(-5.05);
  }
});

test("the δ selector is a labeled preference view that only widens the list", async ({
  page,
}) => {
  const dG = page.getByRole("group", { name: "Delta view" });
  const line = page.getByText(/stored shown \(total /);
  const robustN = parseInt(
    ((await line.textContent()) ?? "").replace(/,/g, ""),
    10,
  );
  await dG.getByRole("button", { name: "0.5", exact: true }).click();
  await expect(
    dG.getByRole("button", { name: "0.5", exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
  // The view is LABELED (§4a: a preference view, never a score change) …
  await expect(page.getByText(/preference view at δ=0\.5/)).toBeVisible();
  await expect(
    page.getByText(
      /stored shown \(total 5%\+ at δ=0\.5, no favor floor\) · inventory: ≥ [\d,]+ legal · sorted by return\(δ=0\.5\)/,
    ),
  ).toBeVisible();
  // … and the objective verdict/floor stays on every card: return(δ) ≥ the
  // robust return on every pair (ΔW(δ) never drops below the floor), so a δ
  // view can only expose MORE pairs past the same floor — never fewer.
  const deltaN = parseInt(
    ((await line.textContent()) ?? "").replace(/,/g, ""),
    10,
  );
  expect(deltaN).toBeGreaterThanOrEqual(robustN);
  const section = page.locator('section[aria-labelledby="pairs"]');
  const cards = section
    .locator("article")
    .filter({ has: page.getByRole("heading", { name: "Buy + sell" }) });
  if ((await cards.count()) > 0) {
    await expect(
      cards.first().getByText("guaranteed ΔW", { exact: true }),
    ).toBeVisible();
  }
  // Back to robust: the label disappears, maximin sort returns.
  await dG.getByRole("button", { name: "robust", exact: true }).click();
  expect(await page.getByText(/preference view at δ=/).count()).toBe(0);
  await expect(page.getByText(/sorted by guaranteed return/)).toBeVisible();
});

test("no dial combination disables — every preset stays clickable", async ({
  page,
}) => {
  const dG = page.getByRole("group", { name: "Delta view" });
  const minG = page.getByRole("group", { name: "Minimum return" });
  const fG = page.getByRole("group", { name: "Favorability floor" });
  for (const label of ["robust", "0", "0.25", "0.5", "0.75", "1"]) {
    await expect(dG.getByRole("button", { name: label, exact: true })).toBeEnabled();
  }
  for (const label of ["1%", "2.5%", "5%", "10%", "20%"]) {
    await expect(minG.getByRole("button", { name: label, exact: true })).toBeEnabled();
  }
  for (const label of ["−10", "−5", "0", "+2.5", "+5", "No floor"]) {
    await expect(fG.getByRole("button", { name: label, exact: true })).toBeEnabled();
  }
  // The tightest corner of the cube is a valid query.
  await minG.getByRole("button", { name: "20%", exact: true }).click();
  await fG.getByRole("button", { name: "+5", exact: true }).click();
  await dG.getByRole("button", { name: "1", exact: true }).click();
  await expect(
    minG.getByRole("button", { name: "20%", exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
  await expect(
    fG.getByRole("button", { name: "+5", exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
  await expect(
    dG.getByRole("button", { name: "1", exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
  await expect(
    page.getByText(/stored shown \(total 20%\+ at δ=1, favor ≥ \+5\)/),
  ).toBeVisible();
  // every button stays enabled even at the tightest combination
  for (const label of ["1%", "2.5%", "5%", "10%"]) {
    await expect(minG.getByRole("button", { name: label, exact: true })).toBeEnabled();
  }
  for (const label of ["−10", "No floor"]) {
    await expect(fG.getByRole("button", { name: label, exact: true })).toBeEnabled();
  }
});

test("pairs render fully behind every dial combo or the empty state is honest", async ({
  page,
}) => {
  const section = page.locator('section[aria-labelledby="pairs"]');
  const minG = page.getByRole("group", { name: "Minimum return" });
  const fG = page.getByRole("group", { name: "Favorability floor" });
  const combos: [string, string][] = [
    ["1%", "−10"],
    ["5%", "−5"], // a return floor UNDER a favor floor — both dials bind
    ["20%", "No floor"],
  ];
  for (const [minL, favL] of combos) {
    // The dials are independent dimensions — click order is free.
    await minG.getByRole("button", { name: minL, exact: true }).click();
    await fG.getByRole("button", { name: favL, exact: true }).click();
    const pairCards = section
      .locator("article")
      .filter({ has: page.getByRole("heading", { name: "Buy + sell" }) });
    const n = await pairCards.count();
    if (n === 0) {
      // Empty filter: the message must quantify what each loosening exposes,
      // or say nothing survives either dial alone.
      await expect(
        section.getByText(
          /No stored pairs with total .* today — (removing the favor floor exposes [\d,]+ stored, dropping the return floor to [\d.]+% exposes [\d,]+|and no stored pair survives either dial alone)/,
        ),
      ).toBeVisible();
      // exact: the board notes contain the phrase "Σv you send", which a
      // substring probe would count; the card chip is exactly "You send".
      expect(await section.getByText("You send", { exact: true }).count()).toBe(0);
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
    // v5 favor is optional in the doc shape too (pre-v5 boards omit it), but
    // present ⇒ a chip on BOTH embedded gate strips (anchored regex — the
    // pair header's "favor: buy …" line never matches) plus the pair line.
    const favorChips = await first.getByText(FAVOR_CHIP).count();
    if (favorChips > 0) {
      expect(favorChips).toBe(2);
      expect(await first.getByText(/favor: buy /).count()).toBe(1);
    }
    await expect(
      first.getByText(/Band ceiling for this package/).first(),
    ).toBeVisible();
  }
});

test("bucket inventory floors are disclosed honestly", async ({ page }) => {
  // Live-data dependent: when any selected favor bucket is saturated, the
  // inventory renders "≥ N" and the verified-floor note appears; when none
  // is (and the dials sit on bucket edges — the defaults do), neither does.
  // (Outside whole-space walks every count is a floor, so both normally show.)
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
