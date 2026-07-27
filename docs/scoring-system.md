# Scoring System v3 — Simple KTC Arbitrage

Chicago Dynasty (Sleeper league `1312124603224555520`, 12-team 1QB dynasty, full PPR; my team: bengramling, roster_id 4). This spec supersedes v2 (never implemented) and v1 (the running engine at the time of writing). It is THE contract: the engine implements it exactly, and its invariants are the test suite.

## 0. Design principles (user-locked, 2026-07-27)

1. **Simple.** The model fits on an index card. Anything that doesn't earn its place is out.
2. **Only reliably computable inputs.** Every number in the scoring path is KTC price data, roster arithmetic, or a fact about a completed transaction. No estimated probabilities, no simulated opponent utilities, no invented constants. (KTC itself "is really a loose estimate" — the user's words — so no precision machinery gets built on top of it.)
3. **Rational roster management is assumed**, for every team including mine. Roster counts and pending cuts are housekeeping, not signals: "just because somebody is over the roster limit, that does not mean that they are a seller."
4. **Strategy**: wealth arbitrage between postures. Sell veteran players to teams that want to win now; buy players from / sell picks to teams that are rebuilding. Every trade pairing ends roster-neutral. Deadlines are execution logistics, not score inputs.

## 1. Data contract

| Input | Source | Rule |
|---|---|---|
| Player value `v(a)` | KTC `oneQBValues.value` (0–9999), joined via `data/ktc_sleeper_map.json` crosswalk | Canonical. Never superflex, never TEP variants, never production stats. Missing from KTC ⇒ `v = 0` + `unvalued` flag (display "—", never treat 0 as truth). |
| Pick value `v(p)` | KTC RDP tranche records (`2027 Mid 1st` etc.) | Picks are valued at their KTC tranche number — the number every league-mate sees. Current-year picks additionally display the rookie-board slot-implied value as an annotation (information only; never scored). |
| Rosters, picks, taxi, IR, FAAB | Sleeper API | Refreshed daily + on demand (unchanged collector). |
| Trade history | Sleeper transactions (both league seasons) | Sole source of posture classification (§4). |
| League fairness norms | Measured from this league's completed trades | §3 constants; re-derivable from the transaction log. |

## 2. The score

For any trade (mine or hypothetical between others):

```
ΔW(side) = Σ v(assets received) − Σ v(assets given)
```

That is the entire scoring mechanism. Face KTC value, both directions, players and picks alike.

- `ΔW(me) = −ΔW(them)` on every trade — exact zero-sum, by construction.
- **Nothing else moves the score.** Not my lineup, not anyone's roster count, not pending cuts, not deadlines, not probabilities, not the counterparty's internal valuation. §11's regression invariants enforce each exclusion explicitly.
- A trade is worth surfacing when `ΔW(me) ≥ W_min = 150` (below that is noise inside KTC's own error bars).

## 3. The fairness gate — "would they think it's fair?"

League-mates evaluate trades by checking KTC — the same site this system scrapes. The gate models exactly that check, with tolerances **measured from this league's ~33 completed trades**, not invented:

1. **Adjusted-value band.** `AdjV(package) = Σ cᵢ·v(aᵢ)` with assets sorted by `v` descending and consolidation coefficients `c = (1.00, 0.90, 0.80)` (the observed quantity discount — two mid assets do not equal one stud). Require `|AdjV(give) − AdjV(get)| ≤ max(500, 0.20 · max side)`.
2. **Anti-fleece cap.** Raw `Σv` ratio ≤ **1.35**. Never exempted: fleeces don't clear, and reputation is an asset in an 11-opponent repeated game.
3. **Legality.** Both post-trade rosters legal: positional minima, roster caps with taxi routing per the taxi mechanics (§8), IR rules, trade deadline week 11.

**Proposal policy (v3.1 — the band is a tolerance, not a target):** for any give-package, the engine proposes the get-package with the **smallest in-band gap that still clears `ΔW(me) ≥ W_min`** — the least-favorable trade worth doing. Offers therefore read as nearly fair on KTC (which is why they clear); the band's remaining width is negotiating room, opened via the +8% anchor-ask convention (a card annotation, from v1's observed negotiations); the card also shows the band-edge ceiling as information. Edge comes from running near-fair trades repeatedly in the right direction, never from gouging on a single leg. (v3.0 proposed the band-edge package on every leg — offers at the maximum gap the league has ever tolerated read as attempted fleeces and were rejected in practice; user: "extremely lopsided roster-neutral trades that nobody would ever take.")

## 4. Targeting — "who do I call, and what do I offer?" (qualitative only)

Posture is classified from **observed trades only**, over the trailing 12 months:

```
For each team: count completed trades where net flow = players in / picks out ("bought"),
and the reverse ("sold"). BUYER if bought ≥ sold+1 and bought ≥ 2 · SELLER mirrored ·
else NEUTRAL. Inactive (< 2 trades) ⇒ NEUTRAL.
```

Each label is displayed **with its evidence** (the trades that produced it) and is user-overridable per team. Labels order and annotate recommendations; they never gate and never score.

- **Offer shape:** veteran players → BUYERs; picks → SELLERs; NEUTRAL teams see both, ranked lower.
- **Aim at visible holes:** each team's per-position starting-lineup sums (league-tab arithmetic) annotate *which* players to offer a BUYER — information for the user, not a score term.
- **Two offers to the same team are noted** ("also proposed to jaketoppen") — appetite is finite, but modeling it is psychology, which stays with the user.

## 5. Pairings, the book, and execution

- **The recommendation unit is the PAIR, fully count-neutral (v3.2, strict):** a **buy side** (I receive a player, paying picks — aimed at SELLER-posture counterparties) matched with a **sell side** (I send player(s) for picks — aimed at BUYERs), sharing no assets, and netting — for my side — **exactly `Δ(player count) = 0` AND `Δ(pick count) = 0`** ("completely neutral: we should end with the same amount of picks and same amount of players as before"). Players count wherever they land (active or taxi); picks count as picks regardless of year. No executed plan may inflate either inventory: the bundling wedge is harvested as value-per-slot upgrades at constant counts, never as asset-count accumulation. **Unpaired legs of any direction are building blocks, not executable recommendations** — sells and neutrals list in a labeled secondary section with their count deltas; buys with no exit sit on the watch list with the blocker named.
- **Ranking:** pairs by posture fit first (both legs fit their counterparty's label/intel), then combined `ΔW(me)`; sell-legs likewise. All legs individually pass §3. Shared-asset conflicts across displayed items carry `exclusive_with`.
- **Execution protocol (rules, not math):** agreement-first — negotiate the buy to a verbal yes, execute the sell-leg, execute the buy minutes later (Sleeper trades process instantly, `trade_review_days = 0`). With open roster spots the buy may execute first; at the cap, sell first. Don't publicly fire-sale before making buy-side asks. After any executed trade, the whole board recomputes from fresh rosters.

## 6. Waiver tab

Mechanics carried from v1 (they were already empirical):

- **Claim score** `= v(add) − v(drop)`, drop = my lowest-`v` active (rational housekeeping). Positive-score claims list with the drop named.
- **Bids:** offseason $0 default / $1 when contested (waivers process daily, budget $50 until ~Aug 12 then $200); in-season ladder exactly as v1 §6.4 with its two 2025 backtests (Waller $63 vs actual $60; Kyler $117 vs actual $115) — the in-season formula's `ΔL` allocates FAAB dollars to weekly lineup needs, a separate currency from trade wealth, explicitly outside the no-lineup-term rule which governs trades.
- **Drop list:** actives ascending by `v` — informational housekeeping.
- **Taxi fill:** pre-lock, surplus free taxi slots (slots beyond incoming-pick needs — pure arithmetic) list the best stashable 1st/2nd-year FAs; an empty locked slot is worth zero.

## 7. League tab

- **Strength map** (carried): per-team per-position starting-lineup sums and ranks; strictly separated **future assets** (picks at tranche + taxi values). Informational.
- **Market map** (new): each team's posture label with its evidence trades, positional holes, pick inventory, FAAB. This is the targeting console.

## 8. Roster mechanics (factual league rules, carried)

Taxi errata 9–12 semantics (1st/2nd-year only, week-4 lock, promote-anytime, slots not refillable post-lock, surplus-slot routing for incoming eligible players), IR eligibility (game-status OUT, 2 slots), positional minima, week-11 trade deadline. These affect **legality and sequencing only** — never the score.

## 9. Parameters

| Parameter | Value | Origin |
|---|---|---|
| `W_min` | 150 | Noise floor inside KTC error bars |
| Fairness band | 20% relative, 500 floor | Measured from league trades |
| Consolidation `c` | 1.00 / 0.90 / 0.80 | Measured from league trades |
| Fleece cap | 1.35 | Measured (max observed cleared ratio) |
| Anchor ask | +8% | Observed negotiation convention; display only |
| Posture window | 12 months, min 2 trades | Definitional |
| Waiver bid ladder | v1 §6.4 values | Backtested on 2025 bids |

Nothing else. Posture labels are user-overridable; every parameter above is re-derivable from data.

## 10. Worked examples (2026-07-27 live values; re-pin exact from fixtures at implementation)

1. **Sell-leg:** Mike Evans (4,116) + Courtland Sutton (3,678) → jaketoppen for vishan's 2027 1st + jaketoppen's 2028 4th (≈9,431 total). `ΔW(me) ≈ +1,624`; gap 19.4% — inside the band, at its favorable edge. Shape: players → BUYER (jaketoppen: repeated players-for-picks buys on record) aimed at the league's thinnest WR room.
2. **Pair:** buy Jauan Jennings (3,026) from millj for a 2028 3rd (≈2,483), `ΔW ≈ +543`, gap ~18% in-band — paired with a sell-leg (e.g., a 2026 4th sale) so the bundle nets roster-neutral. Shape: picks → SELLER-classified counterparty.
3. **Gate rejection:** Cam Ward (4,426) for Shedeur Sanders (2,368): `ΔW +2,058` but ratio 1.87 > 1.35 — never surfaced; fleeces don't clear.

## 11. Implementation invariants (the test suite)

1. `ΔW(me) + ΔW(them) = 0` exactly, every trade.
2. **Independence regressions:** perturb every lineup parameter, every roster count, and remove any player from any bench — no recommended trade's `ΔW` changes. Grep-level: the trade scoring path imports nothing from the lineup solver.
3. Fairness gate: a generated recommendation never violates band, cap, or legality; the §10.3 fleece shape is a pinned must-never-emit.
4. Posture labels reproduce deterministically from the transactions fixture; evidence lists match; override wins.
5. Recommended pairs net exactly zero players AND zero picks for my side (v3.2); a player-neutral but pick-inflating pair is a pinned must-never-emit; `exclusive_with` fires on shared assets.
6. Waiver backtests (Waller/Kyler) keep passing verbatim.
7. Zero-value (`unvalued`) players never contribute to `ΔW` silently — cards flag them.
8. Taxi/IR/deadline legality rules (§8) enforced on both rosters of every recommendation.
9. Determinism: identical snapshot ⇒ identical board, byte-for-byte.
10. Full nightly recompute within the v1 Lambda budget (it is strictly cheaper: no solver in the trade path).

## 12. Changelog

- **v1 (2026-07-26):** ω-blended lineup+wealth+crunch score. Superseded: crunch mis-modeled as a per-transaction cost; recommendations were sell-only.
- **v2 (2026-07-27, never implemented):** wealth arbitrage with probabilistic inventory-risk (clearing odds, hazard decay, four-outcome pair EV). Superseded the same day: the probabilities were not computable from available information ("I want the parameters and inputs to come from information that you can reliably and accurately compute").
- **v3.2 (2026-07-27):** neutrality extended to draft capital — a recommended pair nets exactly zero players AND zero picks for my side (user: "this does not account for draft picks… we should end with the same amount of picks and same amount of players as before"); unpaired legs demoted to building blocks.
- **v3.1 (2026-07-27):** proposal policy inverted after first live board review — minimum in-band gap clearing `W_min` instead of band-edge maximization (the band is tolerance, not target), and the board unit is strictly the hedged pair (buy side + sell side); standalone buys never surface. User: "every trade should come with a corresponding hedge… the model is giving me extremely lopsided roster-neutral trades that nobody would ever take."
- **v3 (original):** pure face-value KTC arbitrage. One score (`ΔW`), one gate (observed KTC fairness), qualitative targeting (observed posture + visible holes), roster-neutral pairings, execution protocol as rules. Successive user simplifications removed: counterparty utility simulation ("to determine if they would think the offer is fair we should just use pure KTC math"), roster-count/cut signals ("that does not mean that they are a seller"), and the incoming cut-fodder gate (cancelled — face value both directions, no exceptions).

## Design provenance

v3 was specified directly in conversation with the league owner (2026-07-27), distilling the v2 judged-panel work (four lenses, three verifying judges) down to the subset whose inputs are reliably computable. The v2 panel's durable contributions that survive in v3: the empirically measured fairness norms, the posture-based targeting thesis, the agreement-first/hedge-first execution protocol, and the demand-honesty and exclusive-with card annotations (as qualitative notes).
