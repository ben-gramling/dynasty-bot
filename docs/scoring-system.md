# Scoring System v4 — Two-Coordinate KTC Arbitrage

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

## 2. The score — two objective coordinates, no blend (v4)

The user's ask, verbatim: "a deterministic way to value one of these spreads. I want to know 'Will this trade make my team better and by how much?' If possible, I want an objective calculation that works in all cases." v4 delivers exactly the objectivity that is mathematically available — and no more.

Every trade's effect on a side decomposes into two parameter-free numbers, both pure roster arithmetic on KTC face values:

```
ΔS = change in STARTER value: the max-Σv legal lineup (QB / 2 RB / 3 WR / TE / 2 FLEX)
     solved over active + taxi players at raw KTC v, after minus before
     (taxi startable — promote-anytime, §8; IR and empty slots = 0;
      for a pair, BOTH legs applied together — legs interact through the lineup)
ΔF = change in TOTAL FACE owned: Σ v(in) − Σ v(out), players and picks alike
     (picks at tranche; additive across legs; conserved per leg — §11.1)
```

Any single-number ledger is `ΔW(δ) = ΔS + δ·(ΔF − ΔS)` for some stored-value preference δ — and **δ is a time preference (win-now ↔ win-later), not a measurable fact**. It is bounded for every rational manager: free disposal ⇒ δ ≥ 0; a starter is a stored asset plus the free option of fielding him ⇒ δ ≤ 1. `ΔW(δ)` is linear in δ, so its value across ALL rational preferences ranges exactly between its endpoints: `ΔS` (at δ = 0) and `ΔF` (at δ = 1). Therefore:

- **Verdict (objective, works in all cases):** a spread is better for EVERY rational preference iff `ΔS ≥ 0 AND ΔF ≥ 0`, at least one strict. This is the user's strategy statement formalized — "increase my team's strength by … capturing edge on both legs." Face-only readmits the two-QB disaster; starter-only readmits bench-stripping; the two coordinates police each other. The board recommends ONLY objectively-good spreads.
- **Magnitude (objective):** the gain is the interval `[floor, ceiling] = [min(ΔS, ΔF), max(ΔS, ΔF)]`. The **floor is the guaranteed gain** — the worst case over every rational preference. A single point inside the interval would require choosing a δ; none is chosen, anywhere.
- **Ranking (objective, maximin):** guaranteed floor descending; ceiling descending as tie-break; deterministic ids last. No preference parameter exists in the system.
- **Preference trades are labeled, not scored.** A spread failing one coordinate is not "bad" — it is preference-dependent, and carries an objective breakeven `δ* = ΔS / (ΔS − ΔF)`: the QB case below is good exactly for δ > 0.5 (a rebuilder's trade). The CLI reports the breakeven for any scored proposal; the board never recommends these.
- **The two user QB cases (locked 2026-07-28) restate as verdicts:** 8,000 + 4,000 → 7,000 + 6,000 is (ΔS −1,000, ΔF +1,000) — NOT objectively good, breakeven δ = 0.5. A 5,000 → 6,000 backup upgrade is (ΔS 0, ΔF +1,000) — objectively good, gain 0 to +1,000 (floor 0 ranks it honestly low). A non-starter sold for a same-face pick is (0, ≈0) — the v3.4 reclassification exploit stays dead with no parameter needed.
- **Raw v only.** The S-solve is the greedy per-slot fill (exact for raw Σv), deterministic ties by KTC playerID asc. None of the league-tab lineup machinery — q insurance weights, availability multipliers, replacement values — enters the trade path (§11.2).
- **Per-side, both coordinates.** Each side's (ΔS, ΔF) is computed against its own roster. ΔF is exactly zero-sum across the parties of a leg (§11.1); ΔS is not — deployment differs by roster, which is why both sides of a good spread can genuinely gain.
- **Nothing else moves the score.** Not roster counts, not pending cuts, not deadlines, not probabilities, not the counterparty's internal valuation, and not KTC's consolidation adjustment (that prices trades in §3; it never values them). §11's regression invariants enforce each exclusion explicitly.
- A spread with `0 < floor < W_min = 150` carries a display-level noise note (inside KTC's own error bars), never hidden.

## 3. The fairness gate — "would they think it's fair?"

League-mates evaluate trades by checking KTC — the same site this system scrapes. The gate models exactly that check, with tolerances **measured from this league's ~33 completed trades**, not invented:

1. **Exact calculator band (v3.4).** Packages are compared exactly as KTC's own trade calculator compares them, via the reverse-engineered value-adjustment algorithm (`core.scoring.ktc_adjust`, a faithful port of keeptradecut.com's client-side logic, pinned by §11.11 to 13 live calculator trades captured 2026-07-27). Per side, assets sorted `v` desc, each contributes `(0.05·(v/C)^1.3 + 0.05·(v/(1.05·R))^6 + 0.1)·v` — `C` = top overall KTC value + 80, `R` = largest asset in the whole trade, both computed from the snapshot; a side's 2nd/3rd/4th+ assets below `R/2` take ×0.85/0.70/0.60 haircuts. The per-side sums are mapped back to value space with KTC's exact iterative inverse and the concentrated side is topped up so the final adjusted gap equals KTC's deserved gap. Require `|adjTotal(give) − adjTotal(get)| ≤ max(500, 0.20 · max adjusted side)` — band tolerances stay the league-measured ones. The fitted consolidation coefficients `c = (1.00, 0.90, 0.80)` are retired: they approximated this algorithm, and the adjustment provably does NOT cancel in roster-neutral pairs (≈ +3,377 for {8000, 2000} over {5000, 5000} at equal raw totals — "Value adjustments dont cancel out").
2. **Anti-fleece cap.** Raw `Σv` ratio ≤ **1.35**. Never exempted: fleeces don't clear, and reputation is an asset in an 11-opponent repeated game.
3. **Legality.** Both post-trade rosters legal: positional minima, roster caps with taxi routing per the taxi mechanics (§8), IR rules, trade deadline week 11.

**Enumeration policy (v3.3 — no pruning before pairing):** the engine keeps EVERY in-band, fleece-clean, legality-clean package variant (deduped by asset multiset) — v3.1's "one fairest get per give" pruning starved the pair matcher and is retired ("our pair and prune logic is severely broken"). Selectivity moves to the user's **target return range** (§5; v3.3.1 — min/max over the presets). The band remains a hard per-leg cap; the band-edge ceiling and the +8% anchor-ask convention remain card annotations. `W_min` retires as a gate (kept only as a display-level noise note in the CLI).

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

- **Target return (v4 numerator):** define `return(pair) = guaranteed floor ÷ Σ v(assets I send across both legs)` — the §2 worst-case gain, `min(ΔS, ΔF)` with ΔS combined across both legs, on face-value inventory deployed. The denominator stays face KTC (what the market prices). Legs are pre-ranked inside the pool by isolation floor as a disclosed heuristic; every STORED pair's coordinates are exact combined. Pure stored-value conversions have floor ≈ 0 and fall below the 1% stored universe automatically. **v3.4.1 — the filter is a total-return floor plus a PER-LEG cap.** Define each leg's **market return** `r(leg) = face ΔW(me, leg) ÷ Σ face v I send on that leg` — the single trade's market-visible skim off its counterparty (v3.3's return definition, kept per-leg; the ledger never enters it). The UI supplies two independent dials: **min** = floor on the TOTAL pair return (presets 1 / 2.5 / 5 / 10 / 20%, default 5), and **max** = cap on EACH leg's market return (presets 2.5 / 5 / 10 / 20% or no cap, default no cap) — "the individual return for either of the two legs cannot be greater than [the cap], however I want to see these in descending order by total return (not per-leg return)". The dials are different dimensions, so no min<max coupling exists; the board always sorts by total return desc. Storage is **stratified by max-leg bucket**: pairs bucket by `max(r(buy), r(sell))` over the half-open bands (−∞,2.5), [2.5,5), [5,10), [10,20), [20,∞); the nightly run keeps the top `pairs_per_band` (100) per bucket sorted by TOTAL return desc, with per-bucket honest counts plus a bucket × total-return-band count grid so the inventory line is honest for any (min, cap) combination (`bands`: {lo, hi, stored, count, saturated, by_total} — **every count is a verified floor, v3.4**: the walks cross legs ordered by their ISOLATION ΔWs, a disclosed pre-ranking heuristic, while each kept pair is priced by its EXACT combined ledger, and the two orderings disagree wherever legs interact — no cutoff can certify the space above it; only a whole-crossing-space walk can, firing only in markets sparse enough to afford it). A cap preset `c` selects the union of buckets with `hi ≤ c` (the cap is exclusive at exactly `c` — half-open bands); the min filter and the sort run instant client-side. Stored universe: total return ≥ 1% (the lowest preset). Supersedes v3.3.1's total-return band storage, which could not serve a leg-cap query (high-total pairs concentrate their lopsidedness in one leg).
- **Posture is a hard constraint in the engine (v3.3):** the sell side of a pair must go to a **BUYER** (they receive players), the buy side must come from a **SELLER** (they receive picks); **NEUTRAL** counterparties accept either shape. Overrides (`posture-overrides`) apply before constraint evaluation. In the trade-negotiator skill the same constraints are qualitative — user intel can promote/demote a team's effective posture or exclude counterparties entirely.
- **The recommendation unit is the PAIR, fully count-neutral (v3.2, strict):** a **buy side** (I receive a player, paying picks — aimed at SELLER-posture counterparties) matched with a **sell side** (I send player(s) for picks — aimed at BUYERs), sharing no assets, and netting — for my side — **exactly `Δ(player count) = 0` AND `Δ(pick count) = 0`** ("completely neutral: we should end with the same amount of picks and same amount of players as before"). Players count wherever they land (active or taxi); picks count as picks regardless of year. No executed plan may inflate either inventory: the bundling wedge is harvested as value-per-slot upgrades at constant counts, never as asset-count accumulation. **Unpaired legs of any direction are building blocks, not executable recommendations** — sells and neutrals list in a labeled secondary section with their count deltas; buys with no exit sit on the watch list with the blocker named.
- **Ranking (v4 maximin; v3.4.1 filter):** pairs sort by TOTAL `return_pct` (guaranteed-floor return) descending within the user's filter (total floor + per-leg cap), ceiling desc as tie-break; every stored pair passes the §2 objective verdict (ΔS ≥ 0 AND ΔF ≥ 0) — posture fit is no longer a rank key because it is a hard pool constraint (§5 posture bullet); every leg individually passes §3. Pair cards carry an `overlaps` count (shared-asset conflicts against other stored pairs); unpaired-leg data keeps exact `exclusive_with`.
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
| ~~Stored discount `δ`~~ | RETIRED (v4) | The score has zero parameters: two objective coordinates + maximin. δ survives only as the derived, per-trade breakeven the CLI reports on preference trades |
| Fairness band | 20% relative, 500 floor | Measured from league trades |
| KTC adjustment | exact port, zero free parameters | Reverse-engineered from keeptradecut.com `site.min.js`; 13/13 live calculator trades integer-exact (2026-07-27). Supersedes fitted consolidation `c` |
| Fleece cap | 1.35 | Measured (max observed cleared ratio) |
| Anchor ask | +8% | Observed negotiation convention; display only |
| Posture window | 12 months, min 2 trades | Definitional |
| Waiver bid ladder | v1 §6.4 values | Backtested on 2025 bids |

Nothing else. Posture labels are user-overridable; every parameter above is re-derivable from data.

## 10. Worked examples (pinned to the committed `data/` fixtures, 2026-07-26 KTC values)

1. **Sell-leg, gate no (v3.4 flip, v3.5 deflation):** Mike Evans (4,125) + Courtland Sutton (3,674) → jaketoppen for vishan's 2027 1st (7,398) + jaketoppen's 2028 4th (1,759). Ledger: `ΔW(me) = +291.5` (starters −64, stored +355.5 = δ·(1,358 face gained + 64)); `ΔW(them) = +572.5` (starters +1,216, stored −643.5) — per side, no negation, and here BOTH ledgers rise. v3.4 read my side at **+9,093** because the two picks arrived at 100% of face against two WRs sitting just outside my lineup at 0 — the reclassification the stored term deletes. Gate (unchanged by v3.5): KTC's calculator shows 7,799 against 12,339, a **4,540 gap = 36.8%** of the larger side against a 2,468 band ⇒ **REJECTED**. The concentrated 7,398 pick earns a top-up that two mid-tier WRs do not; under v3.3's fitted consolidation curve the same trade read 17.3% and passed. Anti-fleece is clean (1.17).
2. **Buy-leg, stored for stored (v3.5 semantics):** buy Jauan Jennings (3,001) from millj for my 2028 3rd (2,468). Ledger: `ΔW(me) = +133.2` (starters 0, stored +133.2 = δ·533) — Jennings does not crack my max-Σv lineup, so v3.4 scored this as a pure `−2,468` pick spend; v3.5 prices it as what it is, a swap *inside* the stored class worth δ of the face picked up. Buy legs can still go negative in isolation (a pick package for a player who never starts), which is why the per-leg return floor stays retired — but the routine ones no longer do. Gate: 2,468 against 3,898, a **1,430 gap = 36.7%** against a 780 band ⇒ **REJECTED** (ratio 1.22, clean). Shape is still right: picks → SELLER-classified counterparty.
3. **Gate rejection:** Cam Ward (4,426) for Shedeur Sanders (2,368): ratio 1.87 > 1.35 — never surfaced; fleeces don't clear.
4. **Both ledgers gain (the arbitrage, §2):** my Javonte Williams (5,460) ↔ ronakpatel32's Zay Flowers (5,651), no picks either way. `ΔW(me) = +191` (starters +191, stored 0 — the entire face gain lands in the lineup, so nothing is left over to discount), `ΔW(them) = +24.2` (starters +96, stored −71.8 — they ship 191 more face than they take back) — the sum is positive because each side's starting lineup improves; zero-sum would have made this impossible to see. Gate PASS. It is the fixture's only gate-clean 1-for-1 where both ledgers rise, which is exactly why §11.1 pins it.

## 11. Implementation invariants (the test suite)

1. **Face conservation:** on every leg, Σ face v leaving one side equals Σ face v arriving at the other, exactly — equivalently, `ΔF(side A) = −ΔF(side B)` on every leg. `ΔS` is per-side (deployment differs by roster) — a pinned example shows a pair where BOTH sides' verdicts are good.
2. **Independence regressions:** perturb every league-tab lineup parameter (`q_*`, `u_*`, replacement) and every roster count — no recommended pair's coordinates change. An uninvolved bench player moves neither `ΔS` nor `ΔF` of any trade. Grep-level: the trade path imports only the raw starter-sum solve, never the q/u/replacement machinery.
3. Fairness gate: a generated recommendation never violates the exact-adjusted band, the fleece cap, or legality; the §10.3 fleece shape is a pinned must-never-emit.
4. Posture labels reproduce deterministically from the transactions fixture; evidence lists match; override wins.
5. Recommended pairs net exactly zero players AND zero picks for my side (v3.2); a player-neutral but pick-inflating pair is a pinned must-never-emit; `exclusive_with` fires on shared assets.
6. Waiver backtests (Waller/Kyler) keep passing verbatim.
7. Zero-value (`unvalued`) players never contribute to `ΔW` silently — cards flag them.
8. Taxi/IR/deadline legality rules (§8) enforced on both rosters of every recommendation; taxi players are startable in `S` (promote-anytime) and otherwise count only in face, IR players in neither.
8b. **v4 coordinate pins:** (a) the two §2 QB cases produce (−1,000, +1,000) → NOT objectively good with breakeven δ* = 0.5 exactly, and (0, +1,000) → good with floor 0; (b) a non-starter sold for a same-face pick has floor ≈ 0 and never enters the stored board (the reclassification exploit stays dead, parameter-free); (c) interval endpoints are the δ-extremes: `ΔW(0) = ΔS` and `ΔW(1) = ΔF` for arbitrary fixture trades; (d) every stored pair satisfies `ΔS ≥ 0 AND ΔF ≥ 0` (one strict) — a verdict-violating pair is a must-never-emit; (e) stored order is maximin: floor desc, ceiling desc, id.
9. Determinism: identical snapshot ⇒ identical board, byte-for-byte.
10. Full nightly recompute within the v1 Lambda budget — the raw starter-sum solve enters the trade path (v3.4) via an incremental exact evaluator (asserted equal to a full re-solve over the fixture rosters and seeded random deltas), and the exact KTC gate runs behind a necessary-condition screen; the budgeted walks still saturate honestly, and under v3.4 every band count is a verified floor (§5).
11. **KTC-adjust port regression:** the 13 captured calculator trades (2026-07-27 values, pinned as fixtures) reproduce integer-exact through `core.scoring.ktc_adjust`; a zero raw-adjustment gap short-circuits to S = 0.

## 12. Changelog

- **v4.0 (2026-07-28):** the blended scalar died; the score became two objective coordinates. From-scratch re-derivation at the user's request ("forget everything… I want to know 'Will this trade make my team better and by how much?' … an objective calculation that works in all cases", with explicit pushback invited on starter-vs-backup and on objectivity). Result: every single-number ledger hides a stored-value preference δ ∈ [0,1] (a time preference, bounded by free disposal below and the fielding option above — not measurable, as the user's own QB example proves: a rebuilder should TAKE the trade the user correctly refuses). v4 therefore reports the two δ-endpoints themselves: ΔS (starter value) and ΔF (face owned). Verdict = both ≥ 0 (the user's strategy sentence, formalized); magnitude = the interval between them, floor guaranteed; ranking = maximin on the floor; preference trades get a derived per-trade breakeven δ* instead of a verdict. v3.5's δ = 0.25 is retired — the framework the user approved with "yes this is great, lets go with that." Starter-vs-backup survived the invited pushback as the ΔS coordinate itself (deployment-dependent value is the source of the arbitrage); the honest residuals are that ΔS measures market value of the deployable nine (not projected points) and that "how much" is irreducibly an interval.
- **v3.5 (2026-07-28):** bench players and picks were unified into one **stored-value** class counted at `δ = 0.25` of face, replacing v3.4's split of bench = 0 / picks = 100%. That seam was farmable: selling a non-starter for a pick of equal value paid ≈ +4,116 of pure reclassification and produced the board's 40%-return pairs, while count-neutrality was the only thing fencing it in. The fix came from the user's two QB cases — "I can only start one QB" (8,000 + 4,000 → 7,000 + 6,000 must be bad) and "a trade that upgrades my bench without decreasing my starters or my picks can still be a good trade" (8,000 + 5,000 → 8,000 + 6,000 must be good) — which bracket δ to (0, 0.5); the midpoint was chosen. Pure deployability (δ = 0) was rejected because it scored the second case at exactly 0.
- **v3.4.1 (2026-07-27):** the board filter's max dial changed dimensions — from a cap on total pair return to a cap on EACH leg's market return (face skim off that counterparty), with the list always sorted by total return desc; storage re-stratified by max-leg bucket with a bucket × total-band honest count grid. User: "filter based on max return for individual trades in a pair. If I set a cap at 5%, this means that the individual return for either of the two legs cannot be greater than 5%, however I want to see these in descending order by total return (not per-leg return)."
- **v3.4 (2026-07-27):** (a) The wealth ledger became STARTER KTC + PICKS KTC: `W = S + P` with `S` the max-Σv starting lineup at raw KTC over active + taxi (bench/IR = 0) and `P` picks at tranche; `ΔW` is per-side and zero-sum is retired (both ledgers can gain — that IS the arbitrage); pair `ΔW` is computed on the combined legs; the per-leg return floor is retired (buy legs are legitimately negative alone). User: "as long as our total STARTER KTC / FUTURE PICKS KTC is increasing, we dont care how that wealth is distributed (studs / lots of solid players). Lets make sure that our trade logic encodes this." (b) The fairness gate's fitted consolidation coefficients were replaced by the exact reverse-engineered KTC calculator adjustment (13/13 live calculator trades integer-exact; the adjustment provably does not cancel across roster-neutral pairs — user: "Value adjustments dont cancel out"). Face KTC remains the market-pricing layer (gate + return denominator); the ledger is what we optimize. Measured at implementation: the exact gate is materially STRICTER than the fitted band it replaces on asymmetric-shape trades (both of §10's old worked examples now fail it — KTC's concentration premium is real and large), and because the pair walk must order legs by their isolation ΔWs while pricing pairs by the non-additive combined ledger, every band count became a verified floor (§5).
- **v1 (2026-07-26):** ω-blended lineup+wealth+crunch score. Superseded: crunch mis-modeled as a per-transaction cost; recommendations were sell-only.
- **v2 (2026-07-27, never implemented):** wealth arbitrage with probabilistic inventory-risk (clearing odds, hazard decay, four-outcome pair EV). Superseded the same day: the probabilities were not computable from available information ("I want the parameters and inputs to come from information that you can reliably and accurately compute").
- **v3.3.1 (2026-07-27):** the min-only return dial became a min/max RANGE over the same presets, and pair storage went stratified — top-100 per return band with per-band honest counts (`bands`) — because top-500-overall storage couldn't serve a range query (all 500 stored pairs sat at the very top of the space). User: "filter... so that i only see the trades within a certain return range."
- **v3.3 (2026-07-27):** prune-then-pair inverted to enumerate-then-filter — full legal pair space computed nightly, user-supplied target return (UI dial; skill takes the same dial with qualitative constraints), posture promoted from annotation to engine constraint (BUYER receives players / SELLER receives picks / NEUTRAL either). User: "our pair and prune logic is severely broken… compute every possible legal trade pair that nets a KTC with that return."
- **v3.2 (2026-07-27):** neutrality extended to draft capital — a recommended pair nets exactly zero players AND zero picks for my side (user: "this does not account for draft picks… we should end with the same amount of picks and same amount of players as before"); unpaired legs demoted to building blocks.
- **v3.1 (2026-07-27):** proposal policy inverted after first live board review — minimum in-band gap clearing `W_min` instead of band-edge maximization (the band is tolerance, not target), and the board unit is strictly the hedged pair (buy side + sell side); standalone buys never surface. User: "every trade should come with a corresponding hedge… the model is giving me extremely lopsided roster-neutral trades that nobody would ever take."
- **v3 (original):** pure face-value KTC arbitrage. One score (`ΔW`), one gate (observed KTC fairness), qualitative targeting (observed posture + visible holes), roster-neutral pairings, execution protocol as rules. Successive user simplifications removed: counterparty utility simulation ("to determine if they would think the offer is fair we should just use pure KTC math"), roster-count/cut signals ("that does not mean that they are a seller"), and the incoming cut-fodder gate (cancelled — face value both directions, no exceptions).

## Design provenance

v3 was specified directly in conversation with the league owner (2026-07-27), distilling the v2 judged-panel work (four lenses, three verifying judges) down to the subset whose inputs are reliably computable. The v2 panel's durable contributions that survive in v3: the empirically measured fairness norms, the posture-based targeting thesis, the agreement-first/hedge-first execution protocol, and the demand-honesty and exclusive-with card annotations (as qualitative notes).
