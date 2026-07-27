# Scoring System v2 — Wealth Arbitrage on a Deadline Book

Team-specific asset valuation for dynasty-bot — Chicago Dynasty (Sleeper league `1312124603224555520`, 12-team 1QB dynasty, full PPR, 4-pt pass TD, lineup QB/2RB/3WR/TE/2FLEX + 10 BN, 3 taxi, 2 IR, FAAB, trade deadline week 11, instant trade processing).

**Design stance (v2 reframe, league-owner mandate).** My side of the market is scored as **pure wealth arbitrage**: maximize +EV in KTC 1QB points, deadline-independent, with **no lineup term in my objective**. Roster compression is a **deadline cost, not a per-transaction cost**: roster-constrained teams happily take players on now, intending to shed others before the binding event (the Aug-15 rookie draft pre-draft; the week-4 taxi lock and week-11 trade deadline in-season). v1's internal inconsistency — its waiver board already reasoned deadline-style ($0 free options because a cut was coming anyway) while its trade engine taxed the identical roster math per transaction, which is why v1 emitted only sell-legs and no buy-leg ever cleared — is resolved by replacing the per-transaction crunch charge on my side with (i) a **hard roster-feasibility constraint at the deadline** and (ii) a probabilistic **inventory-risk charge** on open (unhedged) roster-positive positions that decays to zero as identified closing legs appear and vanishes exactly when one executes.

**The market thesis encoded.** I am the market maker between postures. Contenders (high ω) pay a premium over KTC for lineup points — I **sell players to them, receiving picks**. Rebuilders and deadline-crunched teams (low ω, forced cuts pending) accept below KTC for roster relief and future assets — I **buy players from them, paying picks**. The per-opponent ω surface is the price surface (§5.4); every recommendation is a leg on a **book** that must net roster-feasible by the deadline, and buy-legs open only against **identified hedges** ("we can't trade for 8 players and only give up 1"). Counterparties are unchanged: they are still valued two-sided under **their own ω with the full v1 acceptance machinery** — both legs of every recommendation must actually clear.

Every formula is closed-form and deterministic. All numbers quoted in this document were produced by (or recomputed to the digit against) the live engine on the **2026-07-27 snapshot** (Mongo `dynasty-bot`, last collect 2026-07-27 10:02 UTC; counterparty-side numbers verbatim `scripts/score_trade.py` output). **Landing discipline:** the PR that lands v2 commits this snapshot to `data/` and regenerates every snapshot-marked pin from the committed fixtures; §13 marks each pin `[snap]` (regenerates with the snapshot) or `[struct]` (snapshot-independent — identities, limits, backtests — green before and after the `data/` refresh, so the suite never goes red across the cutover).

---

## 0. Data contract

Carried from v1 unchanged, with two additions (last two rows):

| Input | Source | Rule |
|---|---|---|
| Player value `v(a)` | KTC `oneQBValues.value` (0–9999) joined via crosswalk `ktc_sleeper_map.json` | **Canonical. Never** `superflexValues` (inflates QBs 13–41%), never `tep*`, never production-derived values. Missing from KTC ⇒ `v(a) = 0` + `unvalued` flag (never impute). |
| Rosters, picks, taxi, IR, FAAB | Sleeper API | `taxi[]` and `reserve[]` ⊆ `players[]` — never double-count. Join to KTC **only** via the crosswalk (`playerID` ↔ `player_id`; name/team joins forbidden — 19/464 team disagreements, 5 name variants). |
| Pick values | KTC RDP records (36 generic tranches) + current-year rookie board (`rookie: true` records) | §3.2. Re-verify the 36-tranche set every scrape. |
| 2025 production baselines | `production-baselines-2025.md` | Structural constants only (absence priors `q`, replacement sanity, FAAB calibration). Never a per-player value override. |
| 2025 + 2026 transaction logs | Sleeper | Opponent ω seeds (§2.6), FAAB calibration (§6.4), acceptance priors (§7.3), `p_clear` base-rate sanity (§4.3). |
| Own daily value archive | dynasty-bot snapshot store keyed by KTC `playerID` | DIP flag (§7.6). KTC's embedded `history` is empty in list view — our archive is the only source. |
| Injury status | KTC `injury.*`, Sleeper status | In-season availability multiplier `u(a)` — counterparty lineups only (§9.5). |
| **Plan store** | dynasty-bot collection `plans` | Identified closing legs per shed slot: `{leg_id, shed_sid, counterparty, assets, tier, crowd, p_clear, status ∈ {identified, agreed, abandoned}, created_at}`. Drives π (§4.2). **Auto-seeded nightly** (§4.2 seeding rule); user curation via the trade-negotiator skill is override-by-exception, not a data-entry chore. |
| **Negotiation log** | dynasty-bot collection `negotiations` | Every surfaced recommendation with outcome (executed / declined / expired). Sole calibration source for the January `p_clear` refit (§4.3). |

Snapshot cadence: KTC daily, Sleeper on demand (hourly in-season). Full league recompute bounded per §7.7.

---

## 1. Notation

| Symbol | Meaning |
|---|---|
| `a` | An asset: player or draft pick |
| `v(a)` | KTC 1QB value of a player (0 if unvalued); truth price |
| `P(p)` / `mv(p)` | Pick truth price / market-visible (tranche) price (§3.2); for players `mv(a) = v(a)` |
| `truth(a)` | `v(a)` for players, `P(p)` for picks — one table, all twelve teams, owner-invariant |
| `T` | A team = (players, taxi, reserve/IR, owned picks); `Act(T)` = players − taxi − reserve (19-cap set; IR cap-exempt) |
| `P26(T)` | # current-year picks held (0 after the rookie draft completes) |
| `FT(T)` | Free taxi slots (pre-week-4 lock; vacated slots are dead post-lock — erratum 9) |
| `W(T)` | **Wealth** = Σ `v` over all rostered players (incl. taxi, IR) + Σ `P(p)` over owned picks (= v1's `A(T)`) |
| `k(T)`, `Shed(T)` | Deadline excess (forced-shed count at the next compression event) and the `k` lowest-`v` actives (§4.1) |
| `π_s` | Residual no-buyer probability of shed slot `s` (§4.2) |
| `IRC(T)` | Inventory-risk charge = Σ_s `π_s · v(shed_s)` (§4.2) |
| `ℓ`, `𝔅` | A trade leg; a book = a set of legs (pending or executed) + plan assignments |
| `ΔW(ℓ)` | Σ truth(get) − Σ truth(give) — my wealth delta of a leg |
| `Score_v2(ℓ)`, `M(ℓ)` | `ΔW − ΔIRC` (§5.1); leave-one-out marginal within a book (§5.2) |
| `p_clear(ℓ)` | Clearing probability of a leg: tier prior × crowd haircut, hazard-decayed by days-to-deadline (§4.3) |
| `EV` | Clearing-probability-weighted expected value; the board's ranking key (§7.5) |
| `ω(T)`, `φ_O` | Counterparty contend weight ∈ [0,1]; implied exchange rate `φ_O = ω_O/(1−ω_O)` (§5.4) |
| `L(T)`, `Λ(T)`, `C(T)`, `RV⁰`, `σ⁰` | v1 lineup strength, rookie-augmented lineup, crunch cost, gross retention value `RV⁰(a,O) = ω_O·[L(O)−L(O∖a)] + (1−ω_O)·v(a)`, gross surplus `σ⁰(a,O) = v(a) − RV⁰(a,O)` — **counterparty-side and informational only** (§2) |
| `t_D` | Days to the governing deadline (E1 pre-draft; week-11 in-season). 2026-07-27 → Aug 15: `t_D = 19` |

Units: KTC points throughout; dollars only in the FAAB module. **My side is scored in wealth points only.** ω, `L`, `Λ`, `C`, `q_P`, `R_P`, `ρ_rook` never enter my score (§13 invariant 4).

---

## 2. Counterparty valuation and the lineup model (carried from v1; scope narrowed)

Everything here is **required and unchanged** — it powers (a) the two-sided acceptance model for every counterparty, (b) the League tab, (c) rival waiver demand, and (d) the ΔL transparency line on my cards. It is **never a term in my trade objective**.

### 2.1 Optimal lineup solver (exact, deterministic)

For `pool(T)` (offseason: players − taxi, IR included — July reserve tags are stale; in-season: players − taxi − IR) with `ṽ(a) = u(a)·v(a)`: (1) sort each position descending by `ṽ` (ties by KTC `playerID` asc); (2) starters: top 1 QB, 2 RB, 3 WR, 1 TE; (3) FLEX: top 2 remaining RB∪WR∪TE; (4) unfillable slots take `R_P`. Greedy is provably optimal (FLEX eligibility is a superset of every dedicated slot). The solver reproduces Sleeper `ppts` exactly on 2025 actuals for all 12 rosters (§13.1). One implementation serves counterparty valuation, the League tab, waiver rival demand, and my ΔL transparency diff.

### 2.2 Insurance

`L(T) = Σ_slots (1 − q_P)·ṽ(starter) + q_P·ṽ(backup)`; backup = highest-`ṽ` rostered non-starter of the slot's position (FLEX: flex-eligible), else `R_P`. Defaults `q_QB=.06, q_RB=.14, q_WR=.11, q_TE=.10, q_FLEX=.12`. v1's accepted approximations carried (shared RB backup; a player may back up two slots).

### 2.3 Replacement constants `R_P`

3rd-best **non-rookie** FA per position per snapshot (KTC rookie-flagged FAs always excluded — v1 erratum 7). Live: QB 1,564 · RB 2,220 · WR 2,207 · TE 2,374 · FLEX 2,374.

### 2.4 Rookie now-credit and `Λ` (counterparty side only)

`NC(T) = ρ_rook·[L(pool ∪ E26(T)) − L(pool)]`, `ρ_rook = 0.50`, `Λ = L + NC` — current-year picks enter counterparty lineups as virtual board players (v1 §3.3). Used only inside opponent `Score` and League-tab conventions. My side books picks as pure wealth `P(p)`.

### 2.5 Counterparty transaction score (the v1 core, preserved verbatim)

For any roster change `X` on opponent `O` (in `I`, out `O′`, `T′ = (T∖O′) ∪ I`):

```
Score(X, O) = ω_O·[Λ(T′) − Λ(T)] + (1 − ω_O)·[W(T′) − W(T)] − [C(T′) − C(T)]
```

with `C(T)` the v1 crunch shadow cost on **their** side: `cuts(T) = max(0, |Act| + P26 − 19 − FT)`, `C =` Σ of the `cuts` lowest `RV⁰` among actives, recomputed on every post-transaction roster; taxi wealth debit, surplus stash routing, taxi shadows and `taxi_fill` exactly per errata 9–12. **This asymmetry is deliberate:** opponents are modeled as v1 blended agents (the best predictor of what they accept); I am a wealth arbitrageur (the owner's mandate). `ΔW` is zero-sum across a swap at truth prices; `Score` is not — the difference is where my edge comes from (§5.3).

### 2.6 Opponent ω seeds (behavior-seeded, per-team editable)

| Team | ω | φ = ω/(1−ω) | Basis | | Team | ω | φ | Basis |
|---|---|---|---|---|---|---|---|---|
| jaketoppen | 0.70 | 2.333 | champ; bought Gibbs, DJ Moore, $50 Pacheco | | trdouglas | 0.50 | 1.000 | Bijan core but sold Irving+Burden |
| NoahMoell | 0.65 | 1.857 | two 1sts for Irving+Burden; $115 Kyler | | josbaski | 0.40 | 0.667 | deadline vet-seller; 5 picks in 2027 |
| cmgaither43 | 0.60 | 1.500 | Bowers/Henderson consolidation | | Jukinski | 0.35 | 0.538 | sold Etienne for a 1st |
| joeydavis299 | 0.60 | 1.500 | vet core; barely trades | | ronakpatel32 | 0.35 | 0.538 | sold the 1.03; thinnest roster |
| DrewR87 | 0.60 | 1.500 | top 2025 scorer | | vishan | 0.25 | 0.333 | full teardown |
| millj | 0.55 | 1.222 | runner-up; buys and stacks picks | | | | | |

Auto-refresh suggestion (monthly, manual seed wins): `ω̂ = clamp(0.25 + 0.45·(13 − rank_L)/12 + 0.05·pickflow, 0.20, 0.75)`. In-season ramp: weeks 1–11, seeds 1–6 get `+0.15·w/11`; teams ≥3 games back get `−0.10`.

**Posture-robustness readout (headline, not buried):** every card reprices the **counterparty** side in full (lineup, wealth, crunch) at ω_O ± 0.1 and prints the three verdicts. If the ω−0.1 verdict falls below tier B, the card carries a **POSTURE-FRAGILE** badge — a band-edge extraction that only clears if I've read the counterparty right must say so first-class. (v1's line varied *my* ω; my ω no longer exists as a score input.)

### 2.7 My ΔL: transparency, never score

Every card touching my roster shows `ΔL(me)` from the same solver diff (§12) plus a **starter-degradation guard**: if a leg/book removes a current starter and drops my raw starter sum by more than `starter_guard = 5%`, or leaves any slot unfillable, the card gets a `STARTER-DEGRADATION` badge and requires explicit user confirm. The guard gates display, never the score (§13.4).

---

## 3. Wealth measure and pick pricing

### 3.1 The wealth ledger

`W(T) = Σ_{all rostered players, incl. taxi and IR} v(a) + Σ_{owned picks} P(p)`. My objective is deltas of this ledger at **truth prices**. Zero-sum invariant: for any executed swap, `ΔW(me) + ΔW(them) = 0` — departures debit full `v` wherever the player lives, taxi included (erratum 9).

### 3.2 Pick pricing — concrete truth, tranche perception (carried, re-pinned live)

**Current-year (2026) picks, order known:** overall `n = 12·(round−1) + slot`.

```
P(p)         = board(n)                     — truth, used in W and every ΔW
mv(p)        = tranche(year, band, round)   — market-visible: fairness/anchoring (§7.2) and optics
SellFloor(p) = max(board(n), mv(p))         — minimum acceptable sale return (flag, not filter — erratum 6)
```

`board(n)` = KTC 1QB value of the rank-`n` rookie on the current board (missing ranks interpolate linearly). Bands: slots 1–4 Early, 5–8 Mid, 9–12 Late.

My four 2026 picks (truth / tranche / SellFloor): **1.01 = 7,788 / 6,229 / 7,788** (board(1) = Jeremiyah Love) · **2.09 = 3,239 / 3,510 / 3,510** · **3.03 = 2,940 / 2,847 / 2,940** · **4.01 = 1,946 / 2,036 / 2,036**.

**The anchor wedge** `wedge(p) = mv(p) − P(p)` is v2's currency-selection signal, pinned as a tested vector (§13.10): **2.09 +271 · 4.01 +90 · 3.03 −93 · 1.01 −1,559**. Rule: **spend positive-wedge picks** (the market credits more than they cost me in truth); **never sell negative-wedge picks at anchor** (a 1.01 sold at tranche burns 1,559 truth points — SellFloor enforces ≥ 7,788). The wedge is displayed on cards (`anchor_wedge`) but never added to `ΔW` — counterparty acceptance (§2.5) is conservatively evaluated at truth.

**2027 picks (slot unknown):** tranche with band from the original owner's current `rank_L` (9–12 → Early, 5–8 → Mid, 1–4 → Late). Live band vector: E1 7,404 · M1 6,121 · L1 5,561 · E2 4,512 · M2 4,121 · L2 3,858 · E3 3,029 · M3 2,901 · L3 2,720 · E4 2,169 · M4 2,027 · L4 1,924. `P = mv` (no wedge until the order resolves). **2028 picks:** flat Mid: 5,219 / 3,577 / 2,483 / 1,759. Never extrapolate a future-year premium — read the live RDP records.

**Roll-forward (Aug 15):** 2026 picks cease to exist; drafted rookies become rostered players (taxi-eligible); undrafted rookies rejoin the FA pool; 2027 flips to concrete-board pricing when its order resolves.

### 3.3 Taxi economics (errata 9–12, fully integrated)

House rules: taxi stashable only by 1st/2nd-year players (`seasonsExperience ≤ 1`), fillable until the lock after week 4, promote-out any time, vacated slots dead post-lock.

- `FT(T)` counts in the deadline-excess formula (§4.1): free taxi slots are fungible shed capacity pre-lock.
- **Surplus routing (erratum 10):** an acquired taxi-eligible player who would not crack the starting lineup routes to a *surplus* free slot (`free_taxi − taxi_slot_demand`, `taxi_slot_demand = max(0, |Act| + P26 − 19)`); slots earmarked as deadline absorption are never consumed by stashes. A surplus-routed buy adds **zero** deadline bodies — the one class of buy-leg that needs no hedge (its card says "routes to taxi; self-closing"). My book today: demand 3 > 1 free slot ⇒ no surplus routing available to me.
- **Empty-slot nudge (erratum 12):** an empty surplus slot at the lock is worth exactly zero; a locked stash is a free option — the waiver tab reports `taxi_fill` candidates.
- Week-4 lock: post-lock, departures free no capacity (erratum 9) and `PromoScore` carries `τ_lock = 400` (v1 §9.3 — a counterparty/legality mechanism, unchanged).

---

## 4. Deadline feasibility and the inventory-risk charge (replaces crunch on my side)

### 4.1 The hard constraint

Binding compression events: **E1** Aug-15 rookie draft (every current-year pick converts to a body), **E2** week-4 taxi lock, **E3** week-11 trade deadline, plus continuous in-season legality. Pre-draft:

```
k(T)    = max(0, |Act(T)| + P26(T) − 19 − FT(T))
Shed(T) = the k(T) lowest-v actives (ties: sleeper id asc), skipping any player whose
          removal would break deadline position minimums (≥1 QB, ≥2 RB, ≥3 WR, ≥1 TE)
```

**Feasibility constraint:** the recommended book must reach `k(final) = 0` by E1, and both post-trade rosters of every leg must satisfy v1 legality (positional minima, 9 startable, ≤19 actives after taxi routing or attached drops). In-season there is no deferred window: `k = 0` structurally (no P26), roster caps bind per transaction, and any attached drop's `−v(drop)` is charged **directly inside ΔW** by `apply_tx`. After E3 the sale channel closes: the trades tab disables and unexecuted plans' `p_clear → 0`.

Live `k` vector (2026-07-27): **me 2** (18 actives + 4 P26 − 19 − 1 free taxi) · jaketoppen **0** · ronakpatel32 **0** · NoahMoell 3 · cmgaither43 3 · DrewR87 3 · joeydavis299 4 · vishan 2 · josbaski 2 · Jukinski 4 · millj **6** · trdouglas **6**. My shed: Flacco 910, Diggs 2,622 (next-lowest active: Theo Johnson 2,661).

### 4.2 The inventory-risk charge

An open roster-positive position is inventory that must find a buyer by the deadline or be destroyed. Each shed slot `s` carries the forced-cut downside `v(shed_s)` weighted by the residual no-buyer probability `π_s`:

```
π_s     = Π over identified plans ℓ assigned to s of (1 − p_clear(ℓ))     (empty product = 1)
IRC(T)  = Σ_{s ∈ Shed(T)} π_s · v(shed_s)
```

**Plan store semantics (auto-seeded, override-by-exception):** the nightly run auto-seeds, per shed slot, the best **asset-specific** plan (a passing board leg that sells `shed_s` itself) — at most one per counterparty, best per counterparty only (fills at one shop are correlated). The user may add plans, mark one `agreed` (`p_clear = 1`), or `abandoned`. **Capacity legs (board recommendations that free slots without selling the shed) never auto-attach as plans** — the board must not discount its own risk with its own recommendations; they enter π only when the user marks them as actively pursued, and their execution removes slots from `Shed` outright.

**Plan assignment (deterministic):** asset-specific plans attach to their asset's slot; user-tracked capacity plans attach to unmatched slots in **descending** `v(shed)` order (freed capacity always rescues the most valuable remaining shed — which is also exactly what the `Shed` recount does when a capacity leg executes).

**Decay to zero (the mandate's functional form):** no plan → `π = 1` (a drop is certain destruction); each identified plan multiplies in `(1 − p_clear)`; a plan **executed** removes the slot from `Shed` and the charge is exactly 0. Monotone by construction (§13.6). As `t_D → 0`, `p_clear → 0` (hazard, §4.3) and the charge rises toward the full write-down — open positions correctly become more expensive to carry as the deadline approaches.

**Scope:** IRC is a pre-E1 seasonal window, exactly like v1's `C(T)`. Post-draft, `P26 = 0` and `IRC = 0` league-wide until next year's picks become current. In-season `IRC ≡ 0`; deadline discipline is carried by the hard constraints and the week-11 gate.

### 4.3 `p_clear` — tiered, crowd-conditioned, time-decayed

Every identified leg is tiered by the **preserved v1 acceptance layer** (§7.3) on the counterparty's side; the tier maps to a 30-day base rate, conditioned by crowding and remaining time:

```
q30(tier):  A 0.60 · B 0.35 · C 0.15 · D 0        (tier after Low-activity demotion)
crowd(j,ℓ): only when my package sends j at least one player. pos* = position of the
            highest-mv player sent; bar = v of the player j's own dL_terms displace
            (starter change preferred, else backup change; bar = R_pos* if no lineup change);
            crowd = #{ teams t ∉ {me, j} : t's (slots_pos* + 2)-th best active at pos* has v ≥ bar }
            (slots: QB 1, RB 2, WR 3, TE 1; "+2" leaves room for both flexes — deliberately
            under-counts so only guaranteed rival surplus registers). Picks-only packages: crowd = 0.
q₀        = q30 · max(0.5, 1 − 0.06·crowd)
p_clear   = min(0.90, 1 − (1 − q₀)^(t_D / 30))     agreed legs: p_clear = 1
```

At `t_D = 30`, crowd 0, `p_clear = q30` — the priors keep their calibration meaning. Pinned live values (`t_D = 19`): A/crowd 0 = **0.4403** · A/crowd 5 = **0.2918** · B/crowd 0 = **0.2388** · B/crowd 8 = **0.1195** · C/crowd 0 = **0.0978**. Pinned crowd counts (live rosters): a WR package to jaketoppen displacing starter Malik Washington (3,194) has **crowd 5** (NoahMoell 5,675, DrewR87 4,499, ronakpatel32 4,456, Jukinski 3,482, trdouglas 3,415 all hold a 5th-best active WR ≥ 3,194); one displacing backup Mooney (2,474) has **crowd 8** (those five plus cmgaither43, millj, vishan). Crowding is the missing conditioning the tier alone lacks: a crown-jewel ask into a slot five rivals can fill is priced as perishable; it also prints on the market map (§8).

Calibration: seeds are judgment priors anchored on the league's ~33 trades/12 months (activity priors: High = jaketoppen, cmgaither43, millj, trdouglas, vishan, Jukinski, ronakpatel32; Med = NoahMoell, DrewR87; Low = joeydavis299, josbaski — Low demotes one tier). The negotiation log accrues (surfaced → executed/declined) counts per tier; each January, update `q30(tier)` to the Beta-posterior mean with the seed as a pseudo-count of 10 (same discipline as the `k_need` refit, §6.4).

### 4.4 The hedge requirement

A **buy-leg** is any leg with net `Δ(|Act| + P26) > 0` after taxi routing. Buy-legs are recommendable **only** inside a book whose final state is feasible (`k(final) = 0` at E1) and where every shed slot the buy occupies has an identified closing leg of **tier ≥ B** — (a) a sell-leg to another team, or (b) a scheduled shed with a sale plan (sell-before-drop; a bare drop plan satisfies feasibility but leaves `π = 1` and the full charge). Surplus-taxi-routed buys are exempt (self-closing, §3.3). Buys with no qualifying hedge are never recommended — they appear in the collapsed **watch list** with the blocker named ("+543 vs KTC; needs a closing leg — new shed would be Theo Johnson 2,661 naked").

---

## 5. My objective: the book

### 5.1 Leg score and book EV

```
ΔW(ℓ)         = Σ truth(get) − Σ truth(give)
Score_v2(ℓ|𝔅) = ΔW(ℓ) − [IRC(after 𝔅 ∪ ℓ) − IRC(after 𝔅)]
BookEV(𝔅)     = Σ_{ℓ ∈ 𝔅} ΔW(ℓ) − [IRC(final roster) − IRC(standing book)]
```

IRC is evaluated on the roster with the book's legs applied and remaining shed slots carrying their plan-π's. Legs are always evaluated **jointly** — marginals are not additive (two sell-legs share one capacity release; the v1 "never assume ΔC = 0" discipline, inherited). `BookEV` is a state-function difference, so the **total** is execution-order invariant; only per-leg attribution is path-dependent (§11.1's two-path table; §13.14).

### 5.2 Leave-one-out marginals (order-free attribution)

The canonical per-leg number on every card is `M(ℓ) = BookEV(𝔅) − BookEV(𝔅 ∖ ℓ)`. A leg is recommendable iff `M(ℓ) ≥ W_min = 150` **and** its counterparty side passes the preserved filters (§7.2): `Score(ℓ, O) ≥ 0`, fairness band, anti-fleece, legality.

### 5.3 Where the edge is booked (the market-maker identity)

`ΔW(me) = −ΔW(them)` on every leg, while the counterparty accepts iff `Score(ℓ, O) ≥ 0`. Rearranging, the maximum extractable spread with counterparty effects `ΔΛ_O`, `ΔC_O`:

```
ΔW(me) ≤ [ ω_O·ΔΛ_O − ΔC_O ] / (1 − ω_O)
```

Three edge sources, each named on the card (`spread_source`):

1. **Posture premium** `φ_O·ΔΛ_O` — contenders fund above-truth payments out of lineup gain. Sell-legs.
2. **Crunch subsidy** `−ΔC_O/(1−ω_O)` — a team with forced cuts accepts below-truth sales because the alternative is destruction; a scheduled cut's ask is *exactly zero* (§5.4). Buy-legs. Corollary — **currency selection**: pay crunch-pressed sellers with 2027/2028 picks (bodies out, no P26 in ⇒ relief); pay zero-crunch teams with positive-wedge 2026 picks. A 2026 pick sent to a 6-cut team relieves nothing and kills the deal.
3. **Anchor wedge** — perception minus truth on current-year picks (§3.2); displayed, never booked.

**Structural theorem (the tab states it honestly):** against a crunch-free counterparty, a single buy-leg is never wealth-positive (their floor ≥ truth + φ_O·removal loss ≥ truth); the real buy lane is the **pre-E1 crunch window** — millj (6), trdouglas (6), Jukinski (4), joeydavis299 (4) today — plus DIP timing (flagged, unbooked). This is why v2 pairs sell-side extraction (permanent) with buy-side windows (seasonal), and why the book view exists.

**Demand is finite (grafted discipline):** counterparty appetite is state-dependent and consumed by execution. After any executed leg, every surface, plan, and pending recommendation touching that counterparty is **re-simulated** — spreads are never summed across legs to the same buyer. Pinned (live): after the §11.2 flagship executes, `Bid_jake(Diggs)` collapses **2,736.0 → 798.0** (his WR ladder is now Evans/Sutton-deep and a 21st body would trigger his first crunch cut, dC +547.2), and the re-simulated Diggs plan (→ his remaining 2028 R4) scores **−288.3, tier D, p_clear = 0** — the plan dies, exactly as the exclusive_with label predicted (§7.5).

### 5.4 Per-opponent implied exchange rates — the price surface

For each opponent O and asset/package `G`, computed with the preserved machinery (their solver, their ω, their crunch):

```
Bid_O(G)  = Σv(G) + [ ω_O·ΔΛ_O(+G) − ΔC_O(+G) ] / (1−ω_O)     their rational ceiling to BUY G from me
Ask_O(G)  = Σv(G) + [ ω_O·remΛ_O(G) + ΔC_O(−G) ] / (1−ω_O)    their rational floor to SELL G to me
                                                               (ΔC_O(−G) ≤ 0 is relief; a scheduled cut with
                                                                no lineup role has Ask = v − RV⁰/(1−ω) = 0)
EffBid_O(G) = min( Bid_O(G),  AdjV cap: payment AdjV ≤ AdjV(G)/0.80,  fleece: 1.35·Σmv(G) )
EffAsk_O(G) = max( Ask_O(G),  Σmv(G)/1.35 )        band floor waived when G is all scheduled cuts (erratum 3)
SellEdge = EffBid − Σv        BuyEdge = Σv − EffAsk
```

**Engine identities (tested to 0.1 — §13.9):** `Score_O = (1−ω_O)·(Bid_O(G) − X)` when they pay `X`; `Score_O = (1−ω_O)·(X − Ask_O(G))` when I pay `X`. Pinned live: `Bid_jake(Evans+Sutton) = 7,807 + 2.333·1,294.9 = 10,828.5` ⇒ `0.30·(10,828.5 − 9,431) = 419.2` — matches the engine verbatim. `Ask_millj(Jennings) = 3,026 − 1,361.7/0.45 = 0.0` exactly ⇒ `0.45·(2,483 − 0) = 1,117.4` vs engine 1,117.3 ✓. (These identities also generate the ω±0.1 lines in closed form.)

**How much spread is extractably real** = the Eff-capped edge, reduced further by *pick granularity* (payments come in discrete denominations) and realized only at `p_clear`. Pinned: flagship package — premium capacity 2.333·1,294.9 = 3,021.4 ⇒ raw Bid 10,828.5, but the **fairness band binds**: payment AdjV ≤ 7,437.3/0.80 = **9,296.6**; chosen package AdjV 9,228.3 — extraction **+1,624 of ≈1,700 band-feasible** (the residual is sub-denomination). Jennings — Ask 0.0, fleece floor 3,026/1.35 = 2,241.5 ⇒ max edge **784.5**; extracted 543 (2028 R3 is the nearest denomination). These surfaces populate the market map (§8) and the per-target diagnostic (§7.6).

---

## 6. Waiver tab v2

Outputs unchanged from v1; justification re-derived under the deadline frame. Pool split (rookie-draft inventory read-only while `pre_draft`; claimable veterans ranked) unchanged.

### 6.1 Claims — free options, exactly

Standing drop = head of the shed list **with no identified sale plan** (today: Joe Flacco 910). Three columns per claim of FA `a` (with the standing drop attached; no drop if a slot is open):

```
NetClaim_raw(a)  = v(a) − v(drop)                                  the option's upside
NetClaim_v2(a)   = ΔW − ΔIRC        (book-aware, plan-π's applied)
NetClaim_cold(a) = same at π ≡ 1    (the no-market limit — v1's number, recovered exactly)
```

**Exact swap identities (the free-option rule, deadline-derived — §13.7):** let `m′` = the highest-`v` member of the post-swap shed set. If `a` lands **below the shed line**, `a` replaces the dropped head in `Shed` and `NetClaim_cold = NetClaim_v2 = 0.0` **exactly** — the claim is a free option: strictly better doomed inventory whose raw upside materializes iff a capacity leg lands before E1 (the trades tab's job — "free options are claims fundable by deadline sheds"). If `a` lands above the line, the next-lowest active is pulled onto it and `NetClaim_cold = v(a) − v(m′)`. Pinned live: claim **Ja'Tavion Sanders (2,469)** / drop Flacco → cold **0.0 exactly**, v2 0.0, raw **+1,559** → claim, bid $0. Claim **Greg Dulcich (2,680)** / drop Flacco → **+19.0** = 2,680 − v(Theo 2,661), raw +1,770 → claim, bid $0. Claim when `NetClaim_v2 ≥ −ε` and `NetClaim_raw ≥ N_min = 250`. v1's pinned ≈0 free option is the `π = 1` limit of v2 — the continuity anchor for the whole reframe.

### 6.2 The deadline shed list (replaces the drop queue)

Actives ascending by `v` (pure wealth); the first `k` carry the "due E1" badge. Every row annotates **sell-before-drop**: the assigned plan (counterparty, return, tier, `p_clear`, expected recovery `p·proceeds` vs drop recovery 0), else "no buyer — drop plan, π = 1". Live: 1. **Joe Flacco 910** — no buyer at any price (cheapest pick anywhere is 1,759 → fleece ratio 1.93; π = 1; the write-off §11.2's hedge marginal is credited for avoiding) · 2. **Stefon Diggs 2,622** — plan: → jaketoppen for his own 2027 R4 (tier B, crowd 8, p .1195); `DROP_FLOOR` confirm (`v > 2,500`) applies. In-season, an OUT player with a free IR slot gets the IR move recommended before any drop.

### 6.3 Rival demand (unchanged)

`D(a) = #{j ≠ me: ΔL_j(a) ≥ 300 ∧ FAAB_j ≥ max($1, planned bid)}` with live budgets (cmgaither43/jaketoppen/millj $0 until the ~Aug-12 reset to $200; josbaski $44, ronakpatel32 $45, rest $50).

### 6.4 Bid sizing (carried verbatim — dollars ≠ book)

FAAB prices weekly lineup service in a separate currency. Universal ceiling `bid ≤ NetClaim_raw/κ`, `κ = 25`. Offseason: $0 if D = 0 · $1 if D ≥ 1 · min($3, 6% budget) if D ≥ 2 ∧ raw ≥ 2,000. In-season: `bid = round(min(B_rem·ΔL/k_need·g(D), NetClaim_raw/κ, 0.65·B_rem))`, `k_need = 6,000`, `g = 0.5/1.0/1.15`, stash-only $0 cap $3. Backtests pinned: Waller wk-4 2025 → $63 (actual $60); Kyler wk-11 → $117 (actual $115). January `k_need` refit per v1 §6.4. The `ΔL` here allocates dollars to weekly roster needs and is explicitly outside the no-lineup-term mandate, which governs my **trade** objective.

### 6.5 Taxi fill (erratum 12)

Pre-lock, the board reports `taxi_fill`: top stashable FAs for any surplus free taxi slot.

---

## 7. Trades tab v2: legs, pairs, book

### 7.1 Leg enumeration (carried machinery, wider give-list)

Per opponent: my give-list = **all actives except my top-2 by raw `v`** (cornerstone confirm-gate; still proposable via `score_trade.py`) + all my picks. Their give-list = v1's rule: their top-8 actives by *their* perceived gross surplus `σ⁰(a,O) = v(a) − RV⁰(a,O)` (their model of what they'd shop), + their scheduled cuts, + their picks. Enumerate 1–3 × 1–3 packages; pick-for-pick only when a `P26` count changes. Cheap pre-filters and the per-bucket joint-evaluation budget (`trade_eval_cap_per_bucket = 250`, proxy best-first with the crunch-interaction correction — v1 §13.10/erratum 8) are preserved; my-side evaluation is now **solver-free** (`ΔW` is a truth sum; `ΔIRC` is a k-recount plus a sorted-`v` head), so per-candidate cost drops below v1's. Each survivor classifies by net `Δ(|Act|+P26)` after taxi routing: **sell-leg** (< 0), **neutral**, **buy-leg** (> 0).

### 7.2 Filters (v1, preserved in full)

1. **Fairness band on AdjV:** `AdjV = Σ cᵢ·mv(aᵢ)`, `c = (1.00, 0.90, 0.80)`, mv-based; gap ≤ `max(500, 0.20·max side)`. All-scheduled-cut packages exempt (erratum 3).
2. **Anti-fleece cap:** raw `Σmv` ratio ≤ **1.35**. Never exempted — fleeces don't clear and reputation is an asset in an 11-opponent repeated game.
3. **Legality:** both post-trade rosters (positional minima, 19-cap after taxi routing / attached drops, deadline gating).
4. **Two-sided value:** `M(ℓ) ≥ W_min = 150` (mine, LOO in book context) and `Score(ℓ, O) ≥ 0` (theirs, v1 machinery).

### 7.3 Acceptance layer (v1, preserved)

Posture-fit (contender ω ≥ 0.55 needs `ΔL_O > 0` or biggest-`mv` received is a player; rebuilder ω ≤ 0.40 needs ≥ 50% of raw `Σmv` received in picks + under-25s — erratum 5), tiers A ≥ 300 + fit / B ≥ 100 / C ≥ 0 on `Score_O`, activity demotion, +8% anchor ask, and the §2.6 counterparty ω±0.1 repricing. Tier feeds `p_clear` (§4.3).

### 7.4 Sequencing and information (the two-negotiation reality)

A pair is **two separate negotiations that must both land**. The engine encodes, and the cards state:

- **Hedge-first execution:** never execute a buy-leg while its hedge slot is unsecured — an open position is charged `π·v(shed)` from the moment it opens. Sleeper processes trades instantly (`trade_review_days = 0`), so the **agreement-first protocol** applies: negotiate the buy to agreement (non-binding), execute the hedge/sell, execute the buy minutes later. Walking away from an agreed buy whose hedge died is always allowed — the engine never executes a negative-marginal leg (§7.5's EV encodes exactly this).
- **Information leakage:** executing a visible fire-sale first tells the league I have capacity and weakens my buy-side asks — prefer hedges with *unrelated* counterparties (§11.1's legs touch millj and ronakpatel32; neither reads the other).
- **Recompute-after-execution:** any landed leg re-scores the whole tab and re-simulates every same-counterparty surface (§5.3's consumption discipline).

### 7.5 Pairs, EV, and the book optimizer

- **Pairs:** every buy-leg `b` matches hedge candidates `h` (sell-legs from *other* counterparties, or shed-slot sale plans) sharing no asset, with `Δ(|Act|+P26)(b) + Δ(...)(h) ≤ 0` (roster-neutral or better). Dedup by (buy core asset, hedge core asset) — core = largest-`mv` asset per leg — keeping the best 2 variants by EV.
- **Pair EV (grafted four-outcome form, with the walk-away protocol):** with `S_bs / S_b / S_s` the joint and single-leg `Score_v2` from the standing book and `p_b, p_s` the leg clearing probabilities,

```
EV_pair = p_b·p_s·S_bs + (1−p_b)·p_s·S_s + p_b·(1−p_s)·max(S_b, 0)
```

the last term is the agreement-first walk-away: an agreed buy whose hedge died is executed only if still +EV alone (for a hedge-dependent buy, `S_b < 0` and the branch is worth 0 — priced, not ignored). All four raw outcome scores print on the card.
- **Single-leg EV** = `p_clear·Score_v2`. **Board ranking is by EV** (feasible-first; ties by tier, then deterministic keys) — clearing probability is *in* the ranking, not just displayed, so three thin legs can never outrank one robust one. Tier still displays per leg. Pinned board order (live): flagship EV 1,412.99 > pair EV 405.95 > Diggs-sale EV 204.74.
- **Portfolio honesty (grafted):** displayed items that harvest the same shed slots carry `exclusive_with` references, and the card notes the joint re-score. Pinned: flagship + Diggs-sale jointly = **4,247.75 < 4,842.75** flagship alone (the Diggs sale's marginal after the flagship is **−595.00**) — §13.13.
- **The book:** beam search over the leg pool (top `leg_pool = 60` by standalone EV; beam `W_beam = 32`; depth ≤ `book_depth = 4` — more than 4 simultaneous pending negotiations is not a real plan), maximizing `BookEV` subject to feasibility (`k(final) = 0`), asset-exclusivity, and per-leg `Score_O ≥ 0`. **Tie-breaks (deterministic):** higher `BookEV`, then fewer legs, then lexicographic on the sorted list of (counterparty, core-asset key) per leg. Output: the top book with per-leg LOO marginals and per-leg `p_clear` (and `p_all = Π p_ℓ`, displayed honestly), top 10 pairs league-wide, top 3 legs per opponent, then the watch list.

### 7.6 Market-timing flags (carried)

DIP flag (−6% vs trailing-30-day max, role unchanged → display boost one notch); pick-anchor notes with `below_sell_floor` flag (§11.1's own hedge sells the 4.01 below floor, correctly); the crunch line becomes the **book line**: every card shows `k before → after` and the IRC delta explicitly. The v1 per-target bid/ask diagnostic is reframed on the §5.4 surfaces (their EffBid/EffAsk vs truth, empty zones shown honestly).

### 7.7 Complexity bounds (Lambda budget)

Leg enumeration = v1's budgeted pipeline; the widened my-side give-list roughly doubles raw enumeration, but the per-bucket cap (250) holds joint evaluations at v1's ~10⁴, counterparty solves dominate, and my side is solver-free. Surfaces ≤ 2·11·~20 single-asset evals. Pair matching ≤ `pair_cap = 5,000` O(1) IRC recounts; beam ≤ 60·32·4 ≈ 7,700 O(1) evaluations; plan re-tiering ≤ 33 legs. Budget invariant (§13.16): full nightly recompute ≤ **1.5× the v1 fixture wall-time** on CI (single-digit seconds; the collector Lambda budget is unchanged), with the §11 legs surviving the bucket budget (tested).

---

## 8. League tab

Two strictly separated blocks (lineup strength; future assets — pure `L`; picks at 100% `P` + taxi in `F`) carried from v1, plus the expanded **market map**:

| Team | L | rk | F | ω | φ | axis | k (E1) | crowd-exposure | FAAB |
|---|---|---|---|---|---|---|---|---|---|
| DrewR87 | 52,417.8 | 1 | 45,095 | .60 | 1.50 | MIXED | 3 | | $50 |
| NoahMoell | 51,546.9 | 2 | 35,238 | .65 | 1.86 | BUY (taxed: k 3) | 3 | | $50 |
| cmgaither43 | 51,013.2 | 3 | 47,196 | .60 | 1.50 | MIXED | 3 | | $0 |
| joeydavis299 | 50,487.9 | 4 | 45,903 | .60 | 1.50 | LOW-ACTIVITY | 4 | | $50 |
| **bengramling** | **49,552.5** | **5** | **48,642** | — | — | **MAKER** | **2** | | **$50** |
| jaketoppen | 47,171.5 | 6 | 38,216 | .70 | 2.33 | **BUY (clean: k 0)** | 0 | WR bid crowd 5–8 | $0 |
| trdouglas | 46,504.6 | 7 | 55,845 | .50 | 1.00 | SELL (k 6) | 6 | | $50 |
| ronakpatel32 | 46,202.2 | 8 | 31,268 | .35 | 0.54 | ABSORBER (k 0, 3 taxi) | 0 | | $45 |
| millj | 45,912.6 | 9 | 51,178 | .55 | 1.22 | SELL (k 6) | 6 | | $0 |
| josbaski | 44,996.8 | 10 | 54,784 | .40 | 0.67 | LOW-ACTIVITY | 2 | | $44 |
| Jukinski | 42,130.5 | 11 | 48,524 | .35 | 0.54 | SELL (k 4) | 4 | | $50 |
| vishan | 40,100.8 | 12 | 47,701 | .25 | 0.33 | SELL (k 2) | 2 | | $50 |

Axis = f(ω, k): BUY when ω ≥ 0.55 ∧ k small (jaketoppen is the league's only clean buyer); SELL when k > 0 (forced sheds pending — the pre-E1 buy window); ABSORBER when k = 0 with surplus taxi (takes 2026 picks/bodies at par). **Crowd-exposure** annotates BUY-side teams with the §4.3 crowd count at their weakest slot — how contested (perishable) their bid is. Clicking an edge cell lists per-asset `EffBid`/`EffAsk` rows from §5.4. Per-slot-group starter sums carry from v1 (pinned on the committed fixture); `rank_L` still feeds the 2027 pick bands and the ω auto-refresh.

---

## 9. Edge cases

**9.1 QB2/depth.** Insurance prices depth for opponents and the League tab; my score sees a backup as his `v`, nothing more. Flacco (910) is the canonical illiquid unit: no legal single-leg market exists (cheapest pick 1,759 → fleece ratio 1.93 > 1.35), so his slot charges full `v` until a capacity leg closes it.
**9.2 FLEX competition.** Endogenous in the solver (counterparty valuation and my ΔL transparency); no positional weight table exists anywhere.
**9.3 Taxi promotion.** `PromoScore` with `τ_lock = 400` post-lock (v1 §9.3, unchanged); a promotion that adds an active body is a position like any other.
**9.4 IR.** Strictly game-status OUT, 2 slots, cap-exempt; offseason IR players stay in counterparty pools; IR-before-drop in-season.
**9.5 Offseason vs in-season.** One mode flag. Offseason: `u = 1`, IRC window open, offseason bids. In-season: `u ∈ {1.0, 0.6, 0.25}` in counterparty lineups only (availability never revalues `W`), `IRC ≡ 0` with forced drops charged in ΔW, `t_D` counts to week 11, tab off after week 11, in-season bids.
**9.6 Unvalued players.** `v = 0`, never imputed; permanent shed-list head when rostered; alert if the count grows (stale-crosswalk guard). Live count: 0 (Waller was dropped 2026-07-27).
**9.7 The 1.01.** Truth 7,788 vs anchor 6,229 (wedge −1,559). Selling at anchor burns 1,559 — SellFloor enforces ≥ 7,788-equivalent. Holding costs one deadline body (one of my `P26 = 4`); the book prices that slot at the cheapest alternative shed (today: the 4.01 sale at ΔW −187, §11.1) — so the 1.01 is a firm hold unless someone pays concrete price. v1's "sell bodies first, then hold the 1.01" reproduces as book sequencing.
**9.8 Late current-year picks are liability inventory.** The 4.01 (truth 1,946) occupies a deadline slot worth −910 (the Flacco write-off) if unmanaged; selling it at −187 to a zero-crunch absorber is slot financing — `below_sell_floor` flagged and correct. Shop late 2026 picks to jaketoppen/ronakpatel32, the two k = 0 teams.

---

## 10. Parameters

| Parameter | Default | UI-tunable? | Where |
|---|---|---|---|
| Opponent ω seeds (11) | table §2.6 | Yes (per-team) | §2.6 |
| ω auto-refresh / in-season ramp | 0.25/0.45/0.05 clamp [0.20, 0.75]; +0.15·w/11 / −0.10 | No / Advanced | §2.6 |
| `q_P` priors / `R_P` rule / `u` table / `ρ_rook` | .06/.14/.11/.10/.12 / 3rd non-rookie FA / 1.0/0.6/0.25 / 0.50 | Advanced / No / Advanced / Advanced | §2 |
| Pick regimes + SellFloor | 2026 concrete board; 2027 band by origin `rank_L`; 2028 flat Mid | No | §3.2 |
| **`q30` tier priors** | **A 0.60 / B 0.35 / C 0.15 / D 0** (January Beta refit, pseudo-count 10) | Advanced | §4.3 |
| **Crowd haircut slope / floor** | **0.06 / 0.50** | Advanced | §4.3 |
| **Hazard window / p cap** | **30 days / 0.90** | No | §4.3 |
| **Agreed-plan p** | 1.0 (user-marked) | Yes (per-plan) | §4.2 |
| **Hedge tier minimum** | B | No | §4.4 |
| **`W_min` my-side leg floor (LOO)** | **150** | Yes | §5.2 |
| **`starter_guard`** | 5% starter-sum drop → confirm | Yes | §2.7 |
| **Posture-fragile badge** | verdict < tier B at ω_O − 0.1 | No | §2.6 |
| **Book search `leg_pool`/`W_beam`/`book_depth`/`pair_cap`** | 60 / 32 / 4 / 5,000 | No | §7.5 |
| Deadline calendar | E1 Aug-15 draft; E2 wk-4 lock; E3 wk-11; IRC = 0 post-E1 and in-season | No | §4.1 |
| AdjV coefficients / fairness band / anti-fleece | (1.00, 0.90, 0.80) / 20% ∧ 500 abs (all-cuts exempt) / 1.35 | No / Yes / No | §7.2 |
| Their-side floor / tier A / tier B | 0 / 300 / 100 | Yes / No / No | §7.2–7.3 |
| Posture-fit cutoffs / future share / under-age | 0.55, 0.40 / 50% / 25 | No | §7.3 |
| Max package / give-list / `trade_eval_cap_per_bucket` | 3 per side / all-but-top-2 + picks / 250 | Yes / Advanced / No | §7.1 |
| Anchor-ask markup / DIP threshold | +8% / −6% | Advanced / Yes | §7.3, §7.6 |
| Waivers: `N_min` / ε / `DROP_FLOOR` / rival-ΔL / κ / `k_need` / `g(D)` / clamps / ladders | 250 / 1 / v > 2,500 / 300 / 25 / 6,000 / (0.5, 1.0, 1.15) / 0.65·B_rem / v1 ladder | per v1 | §6 |
| Taxi: `τ_lock` / lock week / eligibility / insurance mult / fill top-N | 400 / 4 / exp ≤ 1 / 0.0 / 5 | per v1 | §3.3 |
| **Removed:** `ω_me` as a scoring knob; mutual-benefit `H` weight (0.30) | — | — | my side has no blend; ranking is EV (§7.5) |

---

## 11. Worked examples (real 2026-07-27 data; counterparty sides verbatim from the live engine; my-side arithmetic exact)

Standing book (me): 18 actives, `P26 = 4` (1.01, 2.09, 3.03, 4.01), `FT = 1` ⇒ **k = 2**; `Shed = {Flacco 910, Diggs 2,622}` (next active: Theo Johnson 2,661). Auto-seeded plans: Flacco — none (π = 1); Diggs — → jaketoppen, own 2027 R4 (tier B, crowd 8, `p = 0.1195`, π = 0.8805). **IRC₀ = 1.0·910 + 0.8805·2,622 = 910 + 2,308.75 = 3,218.75.**

### 11.1 Full arb pair — BUY Jauan Jennings ← millj, hedged by SELL 2026 4.01 → ronakpatel32

```
PAIR (roster-neutral: Δ(bodies+P26) = +1 − 1 = 0; k stays 2; ΔIRC = 0)      S_both = ΔW = +356.00
  BUY leg  (millj, ω .55, activity High, tier B "needs selling", crowd 0, p_clear .2388)
    give 2028 R3 (own) 2,483  →  get Jauan Jennings (WR, 29) 3,026
    my ΔW = 3,026 − 2,483 = +543.0        my ΔL = 0.0 (bench body; transparency line)
    their side (engine, verbatim): dA −543 → 0.45·(−543) = −244.4 · dC −1,361.7 (cuts 6 → 5;
      Jennings is their scheduled cut, RV⁰ = 0.45·3,026 = 1,361.7) · dL 0 ⇒ Score +1,117.3 → tier B
      (contender-fit fails: receives only a pick) · ω-line (their ω, closed-form via §5.4 identity):
      .45 → +1,365.7 · .55 → +1,117.3 · .65 → +869.1 — robust, no badge
    spread source: crunch subsidy. Ask_millj(Jennings) = 3,026 − 1,361.7/0.45 = 0.0;
      fleece floor 3,026/1.35 = 2,241.5 ⇒ max edge 784.5; extracted 543 (denomination: 2028 R3)
    fairness 2,483 vs 3,026 gap 17.9% ≤ 20% ✓ (get side all-cuts ⇒ exempt anyway) · ratio 1.22 ✓
  HEDGE leg (ronakpatel32, ω .35, activity High, tier B, picks-only ⇒ crowd 0, p_clear .2388)
    give 2026 4.01 (truth 1,946, anchor 2,036, wedge +90)  →  get 2028 R4 (own) 1,759
    my ΔW = 1,759 − 1,946 = −187.0
    their side (engine): dA +187 → 0.65·187 = +121.5 ⇒ Score +121.5 → tier B (rebuilder-fit ✓
      100% picks; k=0 absorber with 3 free taxi slots) · fairness gap 13.6% ✓ · ratio 1.16 ✓
    below_sell_floor FLAGGED (SellFloor 2,036 > return 1,759): liability-slot financing —
      the flag is the explanation, not a veto (erratum 6)
  WHY THE HEDGE (the mandate-4 ladder; new shed slot would be Theo Johnson 2,661):
    no closing leg        → ΔIRC = 1.0000·2,661 = 2,661.00 → Score_v2 = 543 − 2,661.00 = −2,118.00  HOLD
    hedge identified      → ΔIRC = 0.7612·2,661 = 2,025.61 → Score_v2 = 543 − 2,025.61 = −1,482.61  HOLD
    hedge executed        → ΔIRC = 0                       → Score_v2 = +543.00                      GO
  OUTCOME TREE (p_b = p_s = .2388, p_both = .0570):
    S_both +356.00 · S_hedge-only +2,121.75 (= −187 + Diggs charge 2,308.75 released)
    S_buy-only −2,118.00 → walk-away branch worth 0
    EV_pair = .0570·356.00 + .1818·2,121.75 + 0 = 20.30 + 385.65 = +405.95
  TWO-PATH EXECUTION (state function; totals telescope — §13.14):
    hedge-first: +2,121.75 then −1,765.75  = +356.00   (mid-path state SAFE: +2,121.75 banked)
    buy-first:   −2,118.00 then +2,474.00  = +356.00   (mid-path state EXPOSED: −2,118.00)
    derived tip: agree buy → execute hedge → execute buy minutes later (instant processing);
    legs touch different teams — no information leakage
```

### 11.2 Hedged/closing single leg — SELL Mike Evans + Courtland Sutton → jaketoppen (board #1)

```
SELL Evans (4,110) + Sutton (3,697) → 2027 R1 (from vishan, Early = 7,404) + 2027 R4 (own, Mid = 2,027)
                                                              my ΔW = 9,431 − 7,807 = +1,624.0
  closing status: net −2 bodies ⇒ k 2 → 0: BOTH shed slots close (Flacco and Diggs stay rostered)
    ΔIRC = 0 − 3,218.75 ⇒ Score_v2 = 1,624 + 3,218.75 = +4,842.75
  their side (engine, verbatim): dL +1,294.9 (WR3 Washington→Evans +815.2 · WR backup
    Mooney→Sutton +403.6 · FLEX backup Mason→Sutton +76.1) ⇒ 0.7·1,294.9 = +906.4 ·
    dA −1,624 → −487.2 · dC 0 (k=0 absorber) ⇒ Score +419.2 ≥ 300, fit ✓ (ΔL > 0) → TIER A
  POSTURE-ROBUSTNESS (headline): ω .60 → +127.3 (tier C) · .70 → +419.2 (A) · .80 → +711.1 (A)
    ⇒ POSTURE-FRAGILE badge: this extraction only clears if jake is really an ω≈.70 buyer
  clearing: crowd 5 (rivals with a 5th active WR ≥ Washington 3,194: NoahMoell, DrewR87,
    ronakpatel32, Jukinski, trdouglas) ⇒ p_clear = .2918 · EV = .2918 × 4,842.75 = 1,412.99
  spread source: posture premium. φ·ΔΛ = 2.333·1,294.9 = 3,021.4 ⇒ raw Bid 10,828.5; binding
    cap = FAIRNESS BAND: payment AdjV ≤ 7,437.3/0.80 = 9,296.6; chosen 9,228.3 —
    extraction 1,624 of ≈1,700 feasible; +8% anchor ask on top per §7.3
  fairness 7,437.3 vs 9,228.3 gap 19.4% ≤ 20% ✓ · ratio 9,431/7,807 = 1.21 ≤ 1.35 ✓
  zero-sum check: ΔW(me) +1,624 = −dA(them) ✓ · my ΔL −228.7 (starter dip 41 = 0.08% of
    51,772 starter sum → no STARTER-DEGRADATION flag)
  v1 contrast (the reframe in one card): v1's flagship was this package for jake's OWN 2027 R1
    (6,121) — my ΔW −1,686, carried by the blended crunch subsidy (v1 scored it +595.1).
    v2 books wealth at truth and demands the vishan R1 + R4: +1,624, and jake still clears
    tier A at +419.2. The bare-R1 variant is dominated and never emitted (§13.12).
```

**The top recommended book** = {11.2 SELL, 11.1 BUY, 11.1 HEDGE}: final state 17 actives, `P26 = 3`, k = 0 ✓. `BookEV = (1,624 + 543 − 187) + 3,218.75 = +5,198.75`; `p` per leg .2918/.2388/.2388. Leave-one-out marginals, all ≥ `W_min`: **M(SELL) = +4,842.75 · M(BUY) = +543.00 · M(HEDGE) = +723.00** (= the 910 Flacco write-off avoided − 187 sale cost). Audited rejections: adding the Diggs→jake sale scores **−595.00** marginal (once k = 0, his 2,622 stays on the ledger — shed-driven sell-legs expire when capacity clears; `exclusive_with` the flagship, §13.13); the Jennings buy *without* its hedge scores **−367.00** marginal (Flacco re-doomed). Sums and marginals reproduce to 0.1.

### 11.3 Inventory-risk case — the standing book, the charge ladder, and demand consumption

```
OPEN POSITION: k = 2 · Shed = {Flacco 910, Diggs 2,622} · IRC by plan state (monotone — §13.6):
  no plans identified:                       IRC = 910 + 2,622                     = 3,532.00
  Diggs plan identified (jake, B, crowd 8):  IRC = 910 + 0.8805·2,622              = 3,218.75
  + second buyer identified (tier C):        IRC = 910 + 0.8805·0.9022·2,622       = 2,992.93
  Diggs plan EXECUTED (sell before drop):    give Diggs 2,622 → get 2027 R4 (own) 2,027
    their side (engine): dL +48.8 (WR backup Mooney→Diggs) · dA +595 ⇒ Score +212.7, tier B
      (band: give side all-cuts ⇒ exempt at gap 22.7%; ratio 1.29 ✓) · ω-line 267.3/212.7/158.0
    my ΔW = −595.0;  k 2 → 1 ⇒ IRC 3,218.75 → 910.00
    Score_v2 = −595 + 2,308.75 = +1,713.75   (sell-before-drop margin: proceeds 2,027 vs drop 0)
    EV = .1195 × 1,713.75 = 204.74 — board #3, exclusive_with the flagship
  k = 0 (post-book):                         IRC = 0                    (charge gone, not waived)
  Flacco slot: no buyer at any price → π = 1; the 910 charge persists until a capacity leg
    (11.1's hedge or 11.2) closes the slot — the write-off M(HEDGE) is credited for avoiding.
DEMAND CONSUMPTION (§5.3, pinned): after 11.2 executes, jake's surface re-simulates:
    Bid_jake(Diggs) 2,736.0 → 798.0 (dΛ → 0 behind Evans/Sutton; a 21st body costs him
    dC +547.2) and the re-simmed Diggs plan (his remaining 2028 R4) scores −288.3, tier D,
    p_clear = 0 — one buyer's appetite is never sold twice.
```

---

## 12. Explainability contract

Every recommendation carries a decomposition object rendered directly (never hand-written); `dL_terms` and lineup audit tables are produced by diffing the same solver call that scored the counterparty side. **Every number shown is reproducible from §§2–7, and displayed components sum to the printed score to 0.1** — leg ΔW's sum to book ΔW; `Score_v2 = ΔW − ΔIRC` on every card; EV reproduces from `p_clear` × outcome scores; LOO marginals recompute from the same engine. Every ΔL is click-expandable to before/after lineup tables; every IRC is click-expandable to its per-slot `π` arithmetic.

Pair card schema (real §11.1 values):

```json
{
  "action": "PAIR",
  "book_id": "2026-07-27-top",
  "buy_leg": {
    "counterparty": "millj",
    "give": [{"type": "pick", "name": "2028 R3 (own)", "truth": 2483, "mv": 2483}],
    "get":  [{"type": "player", "name": "Jauan Jennings", "truth": 3026, "cut_due_them": true}],
    "dW": 543.0, "tier": "B", "posture_fit": false, "activity": "High",
    "clearing": {"q30": 0.35, "crowd": 0, "t_days": 19, "p_clear": 0.2388},
    "spread_source": {"kind": "crunch_subsidy", "their_relief": 1361.7, "ask": 0.0,
                      "floor_binding": "fleece 2241.5", "max_edge": 784.5},
    "them": {"omega": 0.55, "dL": 0.0, "dA": -543.0, "dC": -1361.7, "score": 1117.3,
             "omega_reprice": {"0.45": 1365.7, "0.55": 1117.3, "0.65": 869.1}, "posture_fragile": false},
    "fairness": {"adj": "2483 vs 3026 (gap 17.9%, band 20%, all-cuts exempt)", "raw_ratio": 1.22},
    "my_dL": 0.0, "starter_guard": "pass"
  },
  "hedge_leg": {
    "counterparty": "ronakpatel32",
    "give": [{"type": "pick", "name": "2026 4.01", "truth": 1946, "mv": 2036,
              "pricing": {"rule": "board", "n": 37}, "below_sell_floor": true, "anchor_wedge": 90}],
    "get":  [{"type": "pick", "name": "2028 R4 (own)", "truth": 1759, "mv": 1759}],
    "dW": -187.0, "tier": "B", "posture_fit": true, "activity": "High",
    "clearing": {"q30": 0.35, "crowd": 0, "t_days": 19, "p_clear": 0.2388},
    "them": {"omega": 0.35, "dL": 0.0, "dA": 187.0, "dC": 0.0, "score": 121.5,
             "omega_reprice": {"0.25": 140.3, "0.35": 121.5, "0.45": 102.9}}
  },
  "hedge_status": {"net_bodies_plus_p26": 0, "k_before": 2, "k_after": 2, "dIRC": 0.0,
                   "ladder": {"naked": {"new_shed": "Theo Johnson 2661", "pi": 1.0, "score": -2118.00},
                              "identified": {"pi": 0.7612, "score": -1482.61},
                              "executed": {"score": 543.00}}},
  "pair": {"dW": 356.0,
           "outcomes": {"S_both": 356.00, "S_hedge_only": 2121.75, "S_buy_only": -2118.00,
                        "p_b": 0.2388, "p_s": 0.2388, "p_both": 0.0570},
           "ev": 405.95,
           "two_path": {"hedge_first": [2121.75, -1765.75], "buy_first": [-2118.00, 2474.00], "total": 356.00},
           "sequencing": "agree buy -> execute hedge -> execute buy", "leak_check": "counterparties independent"},
  "book_context": {"loo_marginal_buy": 543.0, "loo_marginal_hedge": 723.0, "book_ev": 5198.75,
                   "exclusive_with": []},
  "audit": {"lineup_tables": "before/after 9-row pairs, counterparty + my transparency diff",
            "irc_expansion": "per shed slot: pi arithmetic q30 -> crowd -> hazard -> pi -> charge"}
}
```

Single legs use the same schema with a `closing_status` (§11.2) or `open_position` (§11.3) block plus `exclusive_with`; CLAIM/DROP/PROMOTE keep the v1 schema with the `bid` block and the shed-list annotation (`netclaim_v2`, `netclaim_cold`, `netclaim_raw`).

---

## 13. Implementation invariants (the v2 test suite)

Each pin is marked `[struct]` (snapshot-independent — stays green across the fixture cutover) or `[snap]` (regenerated together with the committed `data/` snapshot in the landing PR; values below are the 2026-07-27 set).

1. **[struct] Solver ground truth:** the lineup solver reproduces Sleeper `ppts` exactly for all 12 rosters on 2025 actuals.
2. **[struct] Crosswalk guards:** `taxi ⊆ players`, `reserve ⊆ players`; unvalued-rostered count alerts on growth (live count 0); 480–520 KTC assets; 36-RDP set; archive appended.
3. **[struct] Wealth zero-sum across a swap:** for every enumerated leg and the erratum-9 regression (taxi-for-taxi), `ΔW(me) + ΔW(them) = 0` at truth prices; property-based over random legal packages. `[snap]` pin: flagship ±1,624.0.
4. **[struct] No lineup term in my score (the judges' check):** perturb `q_P` (×2), `R_P` (±500), `u`, `ρ_rook`, `taxi_insurance_mult`, and delete `ω_me` — every my-side `Score_v2`, `NetClaim_v2`, `EV`, `BookEV`, and LOO marginal is bit-identical while counterparty Scores move; a code audit asserts the my-side scoring path has no read into `L`, `NC`, or `ω_me`.
5. **[struct] Book roster-neutrality / deadline feasibility:** every recommended pair has net `Δ(|Act|+P26) ≤ 0` with asset-disjoint legs; every recommended buy is hedged (tier ≥ B) or taxi-surplus-routed; the top book ends at `k(final) = 0` with both-side legality on every leg; nothing emitted after week 11; stash routing never consumes demanded taxi slots. `[snap]`: top book = §11.2 + §11.1, final k = 0, BookEV 5,198.75.
6. **[struct] Inventory-charge monotonicity:** IRC non-increasing in added plans, zero on executed closure, non-decreasing in unhedged bodies, `IRC = 0` whenever `k = 0`, post-draft flip zeroes it league-wide; per-slot charge = 0 iff executed or `v = 0`. `[snap]` ladder: 3,532.00 / 3,218.75 / 2,992.93 / 910.00 / 0; unhedged Jennings +2,661.00; identified −ladder −2,118.00 / −1,482.61 / +543.00.
7. **[struct] Free-option exact swap identity:** claiming FA `a` with the plan-less standing drop `h` nets `NetClaim_cold = 0.0` **exactly** when `a` lands below the shed line, and `v(a) − v(m′)` when above (m′ = new marginal shed); `NetClaim_cold` is the π ≡ 1 limit of `NetClaim_v2` (v1's pinned free option recovered). `[snap]`: Sanders 2,469 → 0.0 exactly; Dulcich 2,680 → +19.0 (m′ = Theo 2,661).
8. **[snap] Leg fixtures (my side):** flagship `ΔW +1,624.0`, `Score_v2 +4,842.75`, EV 1,412.99; Jennings `+543.0`; 4.01 hedge `−187.0`; Diggs sale `Score_v2 +1,713.75`, EV 204.74; LOO marginals 4,842.75 / 543.00 / 723.00; rejected marginals −595.00 (Diggs after book) and −367.00 (unhedged Jennings).
9. **[struct] Surface identities to 0.1:** `Score_O = (1−ω_O)·(Bid_O − X)` and `(1−ω_O)·(X − Ask_O)` reproduce the engine for fixed asset sets. `[snap]`: `Bid_jake(Evans+Sutton) = 10,828.5` → 419.2; `Ask_millj(Jennings) = 0.0` → 1,117.4 vs engine 1,117.3.
10. **[snap] Pick fixtures:** 1.01 = 7,788/6,229/7,788 · 2.09 = 3,239/3,510/3,510 · 3.03 = 2,940/2,847/2,940 · 4.01 = 1,946/2,036/2,036; anchor-wedge vector (+271, +90, −93, −1,559) with the currency rule (positive-wedge picks are preferred payment; the 1.01 never sells at anchor); 2027 band vector E1 7,404 … L4 1,924; 2028 flat 5,219/3,577/2,483/1,759; interpolation on missing ranks; `below_sell_floor` on the §11.1 hedge card.
11. **[snap] k-vector & shed fixtures:** (me 2, jake 0, ronak 0, Noah 3, cmg 3, Drew 3, joey 4, vishan 2, josbaski 2, Jukinski 4, millj 6, trdouglas 6); `Shed(me)` = {Flacco 910, Diggs 2,622}, next Theo 2,661; ordering ascending-`v` with sid tiebreak and position-minimum skip.
12. **[snap] Reframe regression (the v2 acceptance test):** v1's flagship at its original price — Evans+Sutton → jaketoppen's own 2027 R1 (`ΔW −1,686`) — is **never emitted**: within the (Evans+Sutton → jake) core, best-2 dedup by EV keeps the vishan-R1+R4 package (EV 1,412.99) and the own-R1+R4 package (`ΔW +341`, them +804.1 tier A, gap 6.4%) and cuts the bare variant. The repriced flagship **is** emitted as board #1. The 4.01 → 2028 R4 sale is emitted with `below_sell_floor`.
13. **[snap] Portfolio cannibalization:** overlapping harvests carry `exclusive_with`; flagship + Diggs-sale jointly = 4,247.75 < 4,842.75 alone; Diggs marginal after the flagship = −595.00.
14. **[struct] State-function telescoping:** for any leg set, Σ sequential attributions = BookEV regardless of execution order (property-based). `[snap]`: §11.1 two-path table — hedge-first +2,121.75/−1,765.75, buy-first −2,118.00/+2,474.00, both totals +356.00 to 0.1.
15. **[snap] Demand consumption:** after any executed leg, same-counterparty surfaces/plans re-simulate; post-flagship `Bid_jake(Diggs)` 2,736.0 → 798.0 and the re-simmed Diggs plan scores −288.3 (tier D, p = 0); spreads to one buyer are never summed without re-simulation.
16. **[struct] Clearing-prior sanity & bounds:** `p_clear` monotone in tier and `t_D`, anti-monotone in crowd, capped at 0.90, = q30 at t_D = 30/crowd 0; January refit consistency vs the trailing-12-month trade count. `[snap]` crowd pins 5 (bar 3,194) and 8 (bar 2,474); p pins .4403/.2918/.2388/.1195/.0978. Bounds: §11 legs survive the 250/bucket budget; pair ≤ 5,000 recounts; beam ≤ 60·32·4; nightly recompute ≤ 1.5× v1 fixture wall-time on CI.
17. **[struct] Acceptance preservation (their side):** fairness band incl. all-cut exemption, 1.35 anti-fleece never exempted, posture-fit letters, tier thresholds, activity demotion, counterparty crunch recomputed post-transaction. `[snap]` pins: jake +419.2 (A, gap 19.4%, ratio 1.21, ω-reprice 127.3/419.2/711.1 with POSTURE-FRAGILE), millj +1,117.3 (B, fit ✗), ronak +121.5 (B, fit ✓, gap 13.6%), Diggs→jake +212.7 (B, band-exempt at 22.7%).
18. **[struct] Explanation = computation; bid backtests; League pins:** card components sum to printed scores within 0.1, `dL_terms` from the scoring solver's own diff, IRC expansions reproduce `q30 → crowd → hazard → π → charge`; Waller wk-4 → $63 and Kyler wk-11 → $117 (actuals $60/$115), offseason board $0s; `[snap]` 12-row L/F table of §8.

---

## 14. v2 changelog — what changed from v1, and why

- **My objective: ω-blend → pure wealth.** v1 scored my side `ω·ΔΛ + (1−ω)·ΔA − ΔC`. The owner's reframe: *"my side is pure wealth arbitrage — +EV in KTC value, deadline-independent."* v2 my-side is `ΔW − ΔIRC`; `ω_me` is deleted from every scoring path (§13.4 makes this a judge-checkable test). Lineup strength survives as League-tab information and a card transparency line with a starter-degradation confirm gate — never a score term.
- **Crunch: per-transaction tax → deadline constraint + inventory risk.** The reframe: *"roster compression is a deadline cost — roster-constrained teams happily take on players now intending to drop/trade others before the deadline,"* and v1 was internally inconsistent: *"the waiver logic already reasoned deadline-style ($0 free options because a cut was coming anyway) while the trade engine taxed the identical roster math per-transaction — which is why v1 recommended only sell-legs and no buy-leg ever cleared."* v2 replaces my-side `C(T)` with the hard `k(final) = 0` feasibility constraint plus `IRC = Σ π·v(shed)` — a P(no-buyer) × forced-cut-downside charge that decays as closing legs are identified and vanishes exactly on execution (§4). v1 is recovered as the π ≡ 1 limit (§6.1, §13.7).
- **Hedges: every buy ships with its closing leg.** *"We can't trade for 8 players and only give up 1"* — buy-legs are recommendable only paired with an identified tier-≥B hedge or surplus-taxi routing; the book nets roster-neutral by the deadline (§4.4, §13.5).
- **The thesis: ω as the price surface.** *"Buy players (paying picks) from rebuilders — they overvalue picks. Sell players (receiving picks) to contenders — they overvalue players."* §5.4 turns each opponent's ω into measurable Bid/Ask surfaces with engine-tested identities, capped by the preserved fairness/anti-fleece machinery to what is *extractably real* — while counterparties are still scored two-sided under their own ω with the full v1 acceptance layer (both legs must clear).
- **Output: recommendations → arb pairs / book view.** Paired buy+sell legs netting roster-neutral with a four-outcome clearing-probability EV, single legs with closing plans and risk status, a beam-searched top book with leave-one-out marginals, exclusive_with labels, and a watch list for blocked buys (§7).
- **New machinery the reframe forced:** clearing probabilities (tier priors × crowding haircut × hazard time-decay, §4.3), the plan store and negotiation log (§0), demand-consumption re-simulation (§5.3), the two-path execution table (§11.1), and EV-based board ranking (§7.5). **Retired:** `ω_me` slider, my-side `C(T)`, my-side `NC`, the mutual-benefit `H` blend.
- **Preserved intact:** the §0 data contract and KTC-1QB canon, the §2 lineup solver and insurance model, §3 pick pricing (concrete-vs-tranche, sell floors), taxi economics errata 9–12, the fairness band + anti-fleece cap + acceptance tiers, the §12 explainability contract, the §13 pinned-fixture discipline, and the full FAAB bid module with its backtests.

## Design provenance

This spec is the synthesis of a four-design judged panel (cumulative scores A 120.5 / B 134 / **C 138 (winner)** / D 123). The architecture is Design C's — the deadline book with plan-π inventory charges, LOO marginals, the EffBid/EffAsk surface, the agreement-first execution protocol, and the max-extraction flagship the other designs left on the table — with every judge-identified defect fixed (beam tie-breaks specified; `σ⁰` defined; the plan store made auto-seeding; the free-option invariant restated as the exact swap identity; the wall-time budget made honest; band-edge asks now clearing-conditioned) and the panel's best grafts folded in: from **B**, the four-outcome pair EV (adapted to the walk-away protocol), the demand-consumption discipline with its re-simulation pin, the `NetClaim_cold` π = 1 column recovering v1's exact 0.0, and the dual-column fixture-landing discipline; from **A**, the crowding haircut and hazard time-decay on clearing priors and the portfolio-cannibalization pin with `exclusive_with` labeling; from **D**, the two-path execution table with the state-function telescoping test, the engine surface-identity pins, and the reframe regression that makes v1's flagship-at-its-original-price a permanent must-not-emit fixture. All worked-example arithmetic was re-verified to the digit against the live engine on the 2026-07-27 snapshot by the synthesizer, including corrections to grafted pins (crowd at the Mooney bar is 8, not 10, under the active-roster definition; all clearing-dependent numbers re-derived with the hazard applied at t_D = 19).
