# Scoring System

Team-specific asset valuation for dynasty-bot — Chicago Dynasty (Sleeper league `1312124603224555520`, 12-team 1QB dynasty, full PPR, 4-pt pass TD, lineup QB/2RB/3WR/TE/2FLEX + 10 BN, 3 taxi, 2 IR, FAAB, trade deadline week 11).

Design stance: **value-to-team is a formal marginal-value computation.** KTC 1QB market value is the single canonical price of every asset; the team-specific part is entirely structural — how much of that price the team can deploy in its expected starting lineup, how much sits as insurance, how much is banked as future assets, and how much is about to be destroyed by roster-spot scarcity. Every formula below is closed-form and deterministic. A reference implementation was run against the 2026-07-26 snapshots (`data/ktc_raw.json`, `data/ktc_sleeper_map.json`, Sleeper rosters/picks) and **every number quoted in this document is reproduced by it exactly.**

---

## 0. Data contract

| Input | Source | Rule |
|---|---|---|
| Player value `v(a)` | KTC `oneQBValues.value` (0–9999) joined via the crosswalk `ktc_sleeper_map.json` | **Canonical. Never** `superflexValues` (inflates QBs 13–41%), never `tep*` (no TE premium here), never production-derived per-player values. Missing from KTC ⇒ `v(a) = 0` + `unvalued` flag (never impute). Currently exactly one rostered case: Darren Waller (Sleeper `2505`). |
| Rosters, picks, taxi, IR, FAAB | Sleeper API (league `1312124603224555520`) | `taxi[]` and `reserve[]` are subsets of `players[]` — never double-count. Join players to KTC **only** via the crosswalk (`playerID` ↔ `player_id`; name/team joins forbidden — 19/464 team disagreements, 5 name variants). |
| Pick values | KTC RDP records (36 generic tranches) + 2026 rookie board (59 `rookie:true` records) | §3.2. Re-verify the 36-tranche set every scrape. |
| 2025 production baselines | `production-baselines-2025.md` | Used **only** for structural constants: absence priors `q`, replacement-structure sanity, bench/flex symmetry, FAAB calibration. Never a per-player value override (locked decision 1). |
| 2025 + 2026 transaction logs | Sleeper | Opponent posture seeds (§5.2), FAAB market calibration (§6.4), acceptance priors (§7.4). |
| Own daily value archive | dynasty-bot snapshot store keyed by KTC `playerID` | Powers the DIP flag (§7.6). KTC's embedded `history` array is empty in list view — our archive is the only source. |
| Injury status | KTC `injury.injuryCode` / `isOutThisWeek`, Sleeper status | In-season availability multiplier `u(a)` only (§9.5). |

Snapshot cadence: KTC daily, Sleeper on demand (hourly in-season). All quantities below are recomputed per snapshot; a full league recompute is sub-second.

---

## 1. Notation

| Symbol | Meaning |
|---|---|
| `a` | An asset: player or draft pick |
| `v(a)` | KTC 1QB value of a player (0 if unvalued); `P(p)` for picks (§3.2) |
| `T` | A team = (players, taxi, reserve/IR, owned picks) |
| `pool(T)` | Lineup-eligible players: **offseason** = players − taxi (IR included — July reserve tags are stale artifacts; reserve players are healthy-next-season assets); **in-season** = players − taxi − IR |
| `Act(T)` | Active roster = players − taxi − reserve (the 19-cap set; IR is cap-exempt) |
| `pos(a)` | QB / RB / WR / TE |
| `Slots` | QB×1, RB×2, WR×3, TE×1, FLEX×2 (FLEX eligible: RB∪WR∪TE) |
| `q_P` | Weekly starter-absence prior for slot type P (§2.2) |
| `R_P` | Free-agent replacement value for position P (§2.3) |
| `u(a)` | In-season availability multiplier (§9.5); `u = 1` for everyone in offseason |
| `L(T)` | Expected starting-lineup strength (§2) |
| `NC(T)` | Rookie now-credit of current-year picks (§3.3); `Λ(T) = L(T) + NC(T)` |
| `A(T)` | Total asset wealth = Σ `v` over all rostered players (incl. taxi, IR) + Σ `P(p)` over owned picks |
| `F(T)` | Future-assets score = Σ `P(p)` + Σ `v(taxi)` (League tab; never mixed into lineup strength) |
| `C(T)` | Roster-crunch shadow cost: value of the forced cuts at the next compression event (§4) |
| `ω(T)` | Contend weight ∈ [0,1] — the contend/build knob (§5.2) |

Units: everything is in KTC points, so lineup deltas, wealth deltas, and crunch are directly commensurable. Dollars appear only in the FAAB module.

---

## 2. Expected lineup strength `L(T)` — the need model

Positional need is never a hand-set weight table; it falls out of a marginal-lineup computation.

### 2.1 Optimal lineup solver (exact, deterministic)

For `pool(T)` with effective values `ṽ(a) = u(a)·v(a)`:

1. Sort each position descending by `ṽ` (ties broken by KTC `playerID` asc — deterministic).
2. Starters: top 1 QB, top 2 RB, top 3 WR, top 1 TE.
3. FLEX: top 2 of the remaining RB∪WR∪TE.
4. Any unfillable slot takes value `R_P`.

Greedy is provably optimal (FLEX eligibility is a superset of every dedicated slot; exchange argument). It is the same solver shape that reproduces Sleeper's `ppts` **exactly** for all 12 rosters on 2025 actuals (`production-baselines-2025.md` §7) — that reproduction is a required unit test (§13), and one implementation serves the lineup model, the League tab, and every trade/waiver evaluation.

### 2.2 Insurance (expected value over absences)

Each slot's starter is absent (injury) with probability `q_P`; the slot then falls to its backup:

```
L(T) = Σ over slots s:  (1 − q_P(s))·ṽ(starter_s) + q_P(s)·ṽ(backup_s)
```

`backup_s` for a QB/RB/WR/TE slot = highest-`ṽ` rostered **non-starter of that position** (an absent RB must be replaced by an RB — the lineup still requires 2 RBs); if none, `R_P`. `backup_FLEX` = highest-`ṽ` flex-eligible non-starter, else `R_FLEX = max(R_RB, R_WR, R_TE)`.

Defaults (injury-absence priors; byes are symmetric across teams and ignored): `q_QB = 0.06, q_RB = 0.14, q_WR = 0.11, q_TE = 0.10, q_FLEX = 0.12`. Accepted approximations: both RB slots share one backup (simultaneous double-absence is O(q²) ≈ 2%); the same player may be both a positional and the FLEX backup.

This term is what gives bench depth and QB2 insurance a real, positive, closed-form value (§9.1) — depth is priced, not guessed, and not zero.

### 2.3 Replacement constants `R_P`

`R_P` = KTC value of the **3rd-best non-rookie free agent** at position P (3rd, so a single claim doesn't move the anchor; KTC rookie-flagged FAs are always excluded from the anchors, per the §10 rule "3rd-best non-rookie FA" — a rookie enters them only when KTC drops the flag, not on draft status; erratum 7 — the `pre_draft` clause governs only §6.1 claimability). Recomputed per snapshot. Current values:

| P | R_P | anchor player | ahead of anchor |
|---|---|---|---|
| QB | 1,562 | Quinn Ewers | Anthony Richardson 2,178 · Will Howard 1,589 |
| RB | 2,207 | Brashard Smith | Emanuel Wilson 2,410 · Isaiah Davis 2,282 |
| WR | 2,202 | Jalen Royals | Jaylin Lane 2,432 · Calvin Ridley 2,278 |
| TE | 2,372 | Colby Parkinson | Greg Dulcich 2,662 · Ja'Tavion Sanders 2,496 |
| FLEX | 2,372 | = max of RB/WR/TE | |

The 2025 production anchors (QB12 ≈ 18.7 ppw, RB24 ≈ 12.1, WR36 ≈ 11.6, TE12 ≈ 11.3, last-flex ≈ 10.1) are the structural justification that one FA-pool replacement line per position is adequate here (RB/WR/TE baselines nearly identical; scarcity lives at the elite end, which KTC's convex curve already prices). They set no player's value.

### 2.4 Current output — my roster (roster 4)

Optimal lineup: QB Burrow 5,744 · RB Jeanty 7,931 + Hampton 7,503 · WR Pierce 4,847 + Addison 4,746 + Evans 4,125 · TE LaPorta 5,195 · FLEX Walker 6,281 + Javonte Williams 5,460. Backups: QB Flacco 919, RB Dowdle 3,830, WR/FLEX Hunter 4,061, TE Theo Johnson 2,673. **L(me) = 49,598.8.**

### 2.5 The locked "5555 WR beats 5555 QB" requirement — synthetic and real

**Synthetic pair (v = 5,555):** a 5,555 WR displaces Evans at WR3 and upgrades the WR/FLEX backups → `ΔL = 0.89·(5555−4125) + 3·0.11·(4125−4061) + 2·0.12·(4125−4061) = +1,309.2`. A 5,555 QB: Burrow (5,744) keeps the slot; only insurance moves → `ΔL = 0.06·(5555−919) = +278.2`. With ω = 0.60 (§5): `VTT(WR) = 3,007.5` vs `VTT(QB) = 2,388.9` — identical market price, WR worth **+26% more to this team**.

**Real same-K pair (regression fixture):** Jameson Williams (WR, ronakpatel32) and Jaxson Dart (QB, vishan) are both exactly **5,408** in the current snapshot. For my roster: JW `ΔL = +1,178.3 → VTT 2,870.2`; Dart `ΔL = +269.3 → VTT 2,324.8` — spread **+545** from the lineup math alone. The requirement generalizes to every position and roster automatically.

---

## 3. Asset wealth, pick pricing, now-credit, future assets

### 3.1 Asset wealth

`A(T) = Σ_{all rostered players, incl. taxi and IR} v(a) + Σ_{owned picks} P(p)`. Raw banked value; used only in deltas.

### 3.2 Pick pricing `P(p)` — concrete truth, tranche perception

**2026 picks (order known; linear draft, all 48 slots resolved):** overall pick `n = 12·(round−1) + slot`.

```
P(p)         = board(n)                       — truth value, used in Score/RV/A/F
MV(p)        = tranche(year, band, round)     — market-visible value, used in the fairness/anchoring layer (§7.2)
SellFloor(p) = max(board(n), MV(p))           — minimum acceptable return when selling
```

- `board(n)` = KTC 1QB value of the rank-`n` rookie on the 59-row 2026 board (present ranks 1–54, 56, 61–64; missing ranks interpolate linearly between neighbors — no slot ≤ 48 is missing today).
- `band`: slot 1–4 Early, 5–8 Mid, 9–12 Late within the round; tranche values from the 36 RDP records.
- Rationale: the rank-`n` rookie is the realizable outcome of holding a known slot — booking the tranche's option premium on your own known mid picks would inflate `F` by ~1–2k/team. But the *market* anchors on tranches, so tranches price the perception layer, and you never sell below `max` of the two.

My four 2026 picks: **1.01 = 7,762** (Jeremiyah Love; tranche 6,243 → SellFloor 7,762) · **2.09 = 3,236** (rank-21; Late-2nd tranche 3,504 → SellFloor 3,504) · **3.03 = 2,927** (SellFloor 2,927) · **4.01 = 1,922** (SellFloor 2,033). Total concrete: 15,847. 1QB caveat: rank-21 is a QB (Ty Simpson); next non-QB is 3,141 (−3%) — board value stands, with a UI flag.

**2027 picks (slot unknown):** tranche with the band projected from the **original owner's** current `rank_L` (draft order is inverse of finish; expected lineup strength is the best available finish predictor): rank 9–12 → Early, 5–8 → Mid, 1–4 → Late. Snapshot values: E1 7,398 · M1 6,118 · L1 5,562 · E2 4,524 · M2 4,139 · L2 3,855 · E3 3,038 · M3 2,889 · L3 2,714 · E4 2,163 · M4 2,036 · L4 1,923. Example: jaketoppen's Jukinski-origin 2027 2nd prices **Early = 4,524** (Jukinski `rank_L` 11).

**2028 picks (two years out):** flat **Mid** tranche (projection two seasons ahead has no signal): 5,207 / 3,579 / 2,468 / 1,759 — full own set = 13,013. Never extrapolate a monotonic future-year premium: the market pays up for next year (2027 E1 7,398 > 2026 E1 6,243) but discounts 2028 below 2027 — always read the live RDP records.

**Roll-forward (Aug 15):** 2026 picks cease to exist; drafted rookies become rostered players; undrafted rookies rejoin the FA pool; when the 2027 order resolves, 2027 flips to concrete-board pricing.

### 3.3 Rookie now-credit `NC(T)` — current-year picks are near-term players

A 2026 pick converts to a body in three weeks; treating it as pure wealth misprices hold-vs-sell decisions (the 1.01's selection would crack my flex). Define the **augmented lineup**:

```
NC(T) = ρ_rook · [ L(pool(T) ∪ E26(T)) − L(pool(T)) ]        ρ_rook = 0.50
Λ(T)  = L(T) + NC(T)
```

`E26(T)` = the expected selections of T's current-year picks (the rank-`n` board players, with their positions), inserted jointly as virtual players. `ρ_rook = 0.50` is structural: 2025's elite rookie class delivered roughly half its dynasty-value-implied lineup impact in year 1 (Jeanty 14.5 ppw). Future-year picks contribute no lineup term.

**Scope:** `NC` lives only inside `Λ` for Score/VTT/RV (waiver/trade decisions). The League tab's lineup strength is pure `L` and its Future block books picks at 100% — locked decision 4 is never violated.

Current: `NC(me) = 1,475.9` — marginal 1.01 (virtual Love displaces Javonte, upgrades RB+FLEX backups) = 1,406.4; marginal 2.09 (virtual Simpson upgrades QB insurance) = 69.5; 3.03/4.01 = 0.

### 3.4 Future assets (League tab metric)

`F(T) = Σ_{picks} P(p) + Σ_{taxi} v(a)` — picks and taxi players only, **never** mixed into lineup strength (locked decision 4). Taxi players are lineup-ineligible, so they are structurally future assets even when veteran.

---

## 4. Roster-crunch shadow cost `C(T)` — spots are priced

Roster spots are a scarce input, and the binding event is the **Aug-15 rookie draft**: every current-year pick converts into a body, actives cap at 19, free taxi slots absorb overflow (`taxi_allow_vets = 1` makes taxi fungible storage until the week-4 lock).

```
cuts(T) = max(0, |Act(T)| + P26(T) − 19 − Fᵗ(T))
   P26(T) = # current-year picks held      Fᵗ(T) = 3 − # taxi slots used
C(T)    = Σ of the cuts(T) lowest RV⁰ among Act(T)
RV⁰(a,T) = ω_T·[L(T) − L(T ∖ a)] + (1−ω_T)·v(a)     (gross retention value — no crunch, no pick credit)
```

`C` is the Score-consistent value of the forced cuts (cutting `a` costs exactly `RV⁰(a)` in §5's units). Every transaction recomputes `C` on the **post-transaction roster** — never assume ΔC = 0 on add+drop swaps: a claimed player who lands below the cut line becomes the new marginal cut and his own gain cancels (this is precisely the failure mode a naive "body-neutral" shortcut ships). After the draft resolves, current-year picks are gone and `cuts(T) = 0` until next year's picks become current — `C` is a seasonal window, not a permanent term.

Computed league-wide today (ω per §5.2):

| Team | cuts | C(T) | cut list | | Team | cuts | C(T) |
|---|---|---|---|---|---|---|---|
| millj | 6 | **6,570.9** | Savion Williams … Jennings | | joeydavis299 | 4 | 3,953.2 |
| trdouglas | 6 | **6,379.3** | Mumpfield … Sean Tucker | | NoahMoell | 3 | 2,764.3 |
| Jukinski | 4 | 5,072.6 | Singletary … Kmet | | cmgaither43 | 3 | 2,137.6 |
| vishan | 2 | 3,560.2 | Engram, Blue | | **bengramling** | **3** | **1,400.9** |
| DrewR87 | 3 | 2,900.4 | Hill, Neal, Mims | | josbaski | 2 | 1,033.5 |
| | | | | | **jaketoppen** | **0** | **0** |
| | | | | | **ronakpatel32** | **0** | **0** |

Market-structure reading the League tab surfaces directly: **jaketoppen and ronakpatel32 are the only teams that can absorb bodies for free** — the natural buyers before Aug 15; millj and trdouglas are motivated sellers. My own crunch: 19/19 active + 4 picks − 1 free taxi ⇒ 3 forced cuts = Waller (RV⁰ 0.0) + Flacco (344.5) + Diggs (1,056.4) = **1,400.9 burned if I do nothing** — which is why the trade engine's top recommendations (§11.2) are body-shedding sales.

---

## 5. Value-to-team: the core scores

### 5.1 Definitions (work for *any* team — mine or an opponent's; that is what makes trades two-sided)

Transaction score for any roster change `X` (assets in set `I`, out set `O`), with `T′ = (T ∖ O) ∪ I`:

```
Score(X, T) = ω(T)·[Λ(T′) − Λ(T)]  +  (1 − ω(T))·[A(T′) − A(T)]  −  [C(T′) − C(T)]
```

Three labeled terms: **Lineup** (win-now: how much more value the weekly lineup deploys, insurance and rookie-credit included), **Wealth** (did we win the trade at market prices / bank future value), **Crunch** (forced-cut value rescued or incurred). Single-asset shorthands:

```
VTT(a, T) = Score(acquire a)                      — acquisition value
RV(a, T)  = −Score(lose a)                        — retention value (crunch-aware; what losing a really costs)
```

Removal cascades bench players up, so `RV` ≠ mirror of `VTT`; packages are always evaluated **jointly** (marginal deltas are not additive — two incoming WRs cannot both claim the same hole, and two outgoing bodies share one crunch relief). Interpretation: a KTC-fair trade converting bench into lineup has ΔA ≈ 0, ΔΛ > 0 — good for a contender. Selling a starter for picks has ΔΛ < 0, ΔA > 0 — good for a rebuilder. Shedding a scheduled cut for anything > 0 is pure profit. The weights arbitrate.

### 5.2 The contend/build knob (locked decision 3, operationalized)

`ω(T)` is the **only** strategy knob: the exchange rate between a lineup point and a banked point.

- **My team: `ω_me = 0.60`** (default; headline UI slider 0–1, labeled "Win-now weight"). 0.60 says a lineup point is worth 1.5× a banked point — contend in 2026, but a clearly-won trade on wealth still gets taken. A lineup-for-wealth swap passes iff `ΔΛ/|ΔA| > (1−ω)/ω = 0.67`; at ω = 0.45 the bar is 1.22 (blend), at 0.75 it is 0.33 (all-in). Moving the slider is exactly "how hard am I contending."
- **Opponents** (the far side of every trade): behavior-seeded defaults from the 2025–26 transaction log, per-team editable in settings:

| Team | ω | Basis (documented behavior) |
|---|---|---|
| jaketoppen | 0.70 | champ; bought Gibbs, DJ Moore, $50 Pacheco with picks |
| NoahMoell | 0.65 | paid two 1sts for Irving+Burden; $115 Kyler bid |
| cmgaither43 | 0.60 | Bowers/Henderson consolidation |
| joeydavis299 | 0.60 | best 2025 record; vet core; barely trades |
| DrewR87 | 0.60 | top 2025 scorer, L rank 1 |
| millj | 0.55 | runner-up; bought Barkley, also stacks picks |
| trdouglas | 0.50 | Bijan/Taylor core but sold Irving+Burden for 1sts |
| josbaski | 0.40 | sold vets at deadline; 5 picks in 2027 |
| Jukinski | 0.35 | sold Etienne for a 1st; L rank 11 |
| ronakpatel32 | 0.35 | sold the 1.03; thinnest roster |
| vishan | 0.25 | full teardown (Barkley → firsts); youngest roster |

- **Auto-refresh (suggestion only, manual override always wins):** monthly, `ω̂(T) = clamp(0.25 + 0.45·(13 − rank_L)/12 + 0.05·pickflow_T, 0.20, 0.75)`, `pickflow ∈ {−1, 0, +1}` = net pick-trading direction over trailing 12 months (bought picks −1, sold +1). The UI shows seed vs formula divergence; the seed wins (rank alone would give the league's most aggressive buyer, jaketoppen, only ~0.55).
- **In-season ramp:** weeks 1–11, playoff seeds 1–6 get `+0.15·w/11`; teams ≥3 games out get `−0.10` (now-points scarcity rises toward the deadline; rebuilders capitulate).

---

## 6. Waiver tab

### 6.1 Pool and ranking

Pool = 214 KTC-valued unrostered players, split hard into two sections:

1. **Rookie-draft inventory** (`rookie: true` while draft `1327016687945392128` is `pre_draft`): 59 players, read-only board display (Jeremiyah Love 7,762 etc. are the picks' value, §3.2) — never claimable. Section auto-dissolves when the draft completes; undrafted rookies then rejoin the claimable list.
2. **True waiver targets** (155 veterans), ranked by crunch-aware **NetClaim**, tiebroken by raw NetClaim:

```
NetClaim(a)     = Score(claim a + the standing drop, me)     (standing drop = head of the §6.2 RV queue; no drop if a slot is open)
NetClaim_raw(a) = same, without the −ΔC term                  (shown as a second column pre-draft)
```

Every claim is scored against the one standing drop — the board answers "what does claiming `a` do to the roster I actually intend to run", not "what is the best possible swap for `a`" (a per-claim best-drop search would surface Richardson's swap-for-Flacco at −22.7 instead of the board's −45.8; that swap is the §6.1 *queued* action instead — erratum 1).

**Free-option rule (pre-draft):** while `cuts(me) > 0`, any add whose post-add `RV⁰` sits below the cut line scores `NetClaim ≈ 0` — the crunch charge exactly cancels his contribution, because he (or an equivalent) is cut on Aug 15. The engine still recommends the claim when `NetClaim ≥ −ε`, `NetClaim_raw ≥ N_min = 250`, and bid = $0: it is strictly-better doomed inventory, and the raw gain materializes if a body-shedding trade lands before the draft. This is the correct July behavior: **don't pay for bodies you're about to cut; sell bodies instead** (§7).

Current top of the board (ω = 0.60; best drop = Darren Waller, RV 0.0):

| Rank | Player | v | ΔL | NetClaim | NetClaim_raw |
|---|---|---|---|---|---|
| 1 | Greg Dulcich TE | 2,662 | 0.0 | **0.0** | +1,064.8 |
| 2 | Ja'Tavion Sanders TE | 2,496 | 0.0 | 0.0 | +998.4 |
| 3 | Jaylin Lane WR | 2,432 | 0.0 | 0.0 | +972.8 |
| 4 | Emanuel Wilson RB | 2,410 | 0.0 | 0.0 | +964.0 |
| … | Anthony Richardson QB | 2,178 | **+75.5** | −45.8 | +893.9 |

(Offseason: no FA cracks the lineup; Richardson is the only ΔL > 0 row — QB2 insurance, §9.1. His swap-for-Flacco scores −22.7 today and **≈ +549 once the draft resolves** — the tab queues it as a post-draft action.)

### 6.2 Drop candidates

Rank actives ascending by crunch-aware `RV` (gross `RV⁰` shown alongside; `DROP_FLOOR`: anything with `RV⁰ > 2,500` requires explicit user confirm). My current queue:

| Player | v | RV (crunch-aware) | RV⁰ (gross) | note |
|---|---|---|---|---|
| Darren Waller TE | 0 | 0.0 | 0.0 | `unvalued`; scheduled cut #1 |
| Stefon Diggs WR | 2,641 | 0.0 | 1,056.4 | scheduled cut #3 |
| Joe Flacco QB | 919 | 11.6 | 344.5 | scheduled cut #2; FA QBs are better insurance (ΔL of keeping him = −38.6) |
| Theo Johnson TE | 2,673 | 30.9 | 1,087.3 | TE backup (+30.1 insurance) |
| Tank Dell WR | 3,122 | 192.4 | 1,248.8 | |

Scheduled cuts (the `cuts(T)` head of the queue) carry an "Aug-15" badge — the standing draft-day drop plan. In-season, if a drop candidate is game-status OUT, recommend the IR slot instead (2 slots, OUT-only).

### 6.3 Rival demand (drives bids)

```
D(a) = #{ teams j ≠ me : ΔL_j(a) ≥ 300  AND  FAAB_j ≥ max($1, planned bid) }
```

computed with each rival's live budget (today: cmgaither43 / jaketoppen / millj at **$0 until the ~Aug-12 reset to $200**; josbaski $44, ronakpatel32 $45, rest $50). Today `D = 0` for every top FA — uncontested daily waivers.

### 6.4 Bid sizing — two modes (locked decision 5)

Mode switches on Sleeper NFL state (`season_type = off/pre` → offseason; `regular` → in-season; budget resets to $200 ~Aug 12 — same as 2025, so 2025 bid history is directly comparable). Universal ceiling in both modes: `bid ≤ NetClaim_raw / κ`, `κ = 25` KTC-points per dollar.

**Offseason mode ($50 budget, daily processing, minimal competition):**

```
bid = $0 if D = 0                (the modal case — 48 of 114 winning 2025 bids were $0)
      $1 if D ≥ 1                ($1 beats the $0 crowd)
      min($3, 6% of budget) if D ≥ 2 and NetClaim_raw ≥ 2,000   (rare)
```

**In-season mode ($200 budget):**

```
bid = round( min(  B_rem · ΔL(a) / k_need · g(D),   NetClaim_raw / κ,   0.65 · B_rem  ) )
k_need = 6,000        g(D): 0.5 if D = 0 · 1.0 if D = 1 · 1.15 if D ≥ 2
stash-only claims (ΔL = 0): $0, cap $3
```

Calibration against this league's real 2025 tape (same $200 budget): emergency startable TE (Waller, wk 4, ΔL ≈ 2,000, B_rem ≈ $190) → model **$63** vs actual winning bid **$60**; playoff-push QB1 stream (Kyler, wk 11, ΔL ≈ 3,500) → **$117** vs actual **$115**. The 0.65 clamp matches the largest bid ever observed here ($126/$200 = 63%); the formula reproduces the $0 median too, since ΔL > 0 is rare with 19-man rosters. **Refit procedure (no hand-waving):** each January, recompute `k_need = median over contested winning claims of (B_rem · ΔL · g(D) / winning_bid)` from the completed season's transaction log; κ and g are fixed constants. (Bankroll-proportional bidding is deliberate: it reproduces how this league actually prices panic.)

---

## 7. Trades tab

### 7.1 Candidate generation

For each opponent `O` (11 teams):

- **My give-list:** my 8 highest assets by gross surplus `σ⁰(a) = v(a) − RV⁰(a, me)` (market price minus gross keep value) **after excluding my top-2 assets by raw `v`** (cornerstone protection — a near-zero backup delta makes Jeanty/Hampton's raw σ⁰ rank first, but cornerstones are not shoppable surplus; erratum 2), **plus all scheduled cuts** (doomed inventory is always shoppable, beyond the 8), plus all my picks. Today: the interchangeable deep-flex block (Walker 2,486, Javonte 2,427, Pierce 2,379, Addison 2,372, Evans 2,331, Hunter 2,327) and the vet bench (Dowdle 2,216, Sutton 2,204, Godwin 2,186, Allgeier 2,006, Diggs 1,585). High-σ⁰ starters are legitimate candidates (I start four RBs); the two-sided filters kill bad star sales.
- **Their give-list:** symmetric, with their `ω`, plus their picks.
- **Enumerate:** every 1–3 × 1–3 package (players and/or picks; picks occupy no roster slot). Pick-for-pick-only swaps included only when either side's `P26` count changes (crunch-motivated).
- **Sequencing:** every candidate is scored against the *current* state; after any executed transaction the whole tab recomputes (overlapping crunch relief across separate proposals is resolved by joint evaluation, never by summing singleton σ's).

### 7.2 Filters (in order, cheap first)

1. **Fairness band on adjusted value (market realism):** package value `AdjV(S) = Σ cᵢ·mv(a₍ᵢ₎)` with assets sorted by `mv` desc, consolidation coefficients `c = (1.00, 0.90, 0.80)` — the market pays a quantity discount (KTC curve: #24 = 6,593 but #96 = 4,479) — and `mv` = **market-visible** value: players at KTC, picks at their generic tranche (what the counterparty sees on KTC). Require `|AdjV(give) − AdjV(get)| ≤ max(500, 0.20·max side)`. 20% reflects observed tolerance (33 trades in 12 months; jaketoppen's DJ-Moore-for-2027-2nd pattern; a 10% band would block the consolidation class this league demonstrably executes). **Packages consisting entirely of scheduled cuts (either side) are exempt from the band** — crunch-arbitrage sales of doomed inventory are the point, not a fairness violation (the §11.2 runner-up, Diggs 2,641 → 2027 4th 2,036, has gap 605 > band 528.2 and is still correct; erratum 3).
2. **Anti-fleece cap:** reject if either side's raw `Σv` exceeds **1.35×** the other's — fleeces don't get accepted, and reputation is a real asset in an 11-opponent repeated game.
3. **Legality:** both post-trade rosters field a full lineup from actives (≥1 QB, ≥2 RB, ≥3 WR, ≥1 TE, 9 total); active count ≤ 19 after modeled taxi-stash (vets legal pre-week-4 lock) or an attached min-RV drop charged to that side's score; deadline: tab disabled after week 11.
4. **Two-sided value:** `Score(X, me) ≥ G_min = 150` **and** `Score(X, O) ≥ 0` — each side scored with its own roster, ω, and crunch. Recommend only trades the counterparty should rationally accept.

### 7.3 Ranking

```
H(X) = Score(X, me) + 0.3 · clip(Score(X, O), 0, Score(X, me))
```

Mutual benefit boosts acceptance probability but never dominates my own gain. Display order is **acceptance tier first (§7.4), then `H` within tier** — an A-tier deal the counterparty should take outranks a bigger-`H` deal that needs selling (erratum 4). Dedup near-duplicates (same core asset pair, keep best 2 variants); show top 10 league-wide + top 3 per opponent, with full decompositions (§12).

### 7.4 Acceptance layer (how it gets said yes to)

- **Posture-fit:** contender (`ω_O ≥ 0.55`) must have `ΔL_O > 0` or the largest-`mv` asset **in the package they receive** must be a player (the best player wins trades in the group chat); rebuilder (`ω_O ≤ 0.40`) must receive ≥ 50% of the package's **raw `Σ mv`** as picks + under-25 players (erratum 5).
- **Tiers:** A = `Score_O ≥ 300` and posture-fit · B = `Score_O ≥ 100` (labeled "needs selling" if fit fails) · C = `0 ≤ Score_O < 100`.
- **Activity prior** (documented deal counts): High = jaketoppen, cmgaither43, millj, trdouglas, vishan, Jukinski, ronakpatel32; Med = NoahMoell, DrewR87; Low = joeydavis299, josbaski. Low-activity partners demote one tier.
- **Anchoring hint:** open ask ≈ +8% above the recommended package on my side.
- **ω-sensitivity line:** every card shows my verdict at ω−0.1 / ω / ω+0.1, so posture-sensitive recommendations are visible as such.

### 7.5 Trade-zone diagnostic (single-target buys)

For a target `t` on team `j`: my ceiling `W = v(t) + (ω/(1−ω))·ΔL_me(t)`; their floor `= v(t) + (ω_j/(1−ω_j))·remΔ_j(t)`. Rendered per named target, honestly including empty zones:

| Target | v | owner | their floor | my ceiling | zone |
|---|---|---|---|---|---|
| Puka Nacua | 8,772 | Jukinski | 11,511 | 15,030 | **+3,519** |
| Malik Nabers | 7,534 | vishan | 8,831 | 12,140 | +3,309 |
| Emeka Egbuka | 6,826 | ronakpatel32 | 8,034 | 10,487 | +2,453 |
| Chris Olave | 6,183 | ronakpatel32 | 7,083 | 8,985 | +1,902 |
| Tetairoa McMillan | 6,951 | josbaski | 9,654 | 10,778 | +1,125 |
| Marvin Harrison Jr. | 5,632 | Jukinski | 6,867 | 7,699 | +832 |
| Ladd McConkey | 6,245 | millj | 9,711 | 9,130 | **none** |
| DK Metcalf | 4,308 | Jukinski | 4,908 | 4,607 | **none** |

The rebuilder-held elite WRs (Nacua, Nabers, Egbuka) are my true buy lane; the actual funding package must still pass §7.2.

### 7.6 Market-timing flags

- **DIP flag:** target's `v` down ≥ 6% from its trailing-30-day max (own snapshot archive) with NFL role unchanged → tag `DIP`, boost display rank one notch. Buying the KTC crowd's overreactions is where fair-band trades become wins.
- **Pick-anchor arbitrage:** counterparties anchor 2026 picks at generic tranches. Sell side: a return below `SellFloor` is **flagged on the card (`below_sell_floor`), not filtered** — crunch-relief sales of liability picks are legitimately below floor (§9.8's own recommendation sells the 4.01, SellFloor 2,033, for a 2028 M4 1,759; erratum 6). The 1.01 must still fetch ≥ **7,762**-equivalent while the market anchors at 6,243. Buy side: others' early 2026 picks offered at tranche-anchored prices are small positive arb (vishan's 1.02: concrete 6,428 vs anchor 6,243).
- **Crunch line:** every trade card that changes body count shows the crunch term explicitly ("cuts 3 → 1: +1,400.9") — each 2026 pick or body traded away is one fewer forced Aug-15 drop.

---

## 8. League tab

One row per team; two strictly separated blocks (locked decision 4) plus a market-map column group. Cells heat-colored by within-column rank; clicking any cell lists the players/picks behind it.

**Lineup strength** — per slot group, the raw sum of assigned starters' `v` from the §2.1 solver, plus expected `L(T)` (insurance-weighted) with rank and z-score. **Future assets** — Picks (Σ `P`, §3.2) and Taxi (Σ `v`) and `F(T)` with rank. **Market map** — ω, Aug-15 `cuts / C(T)`, FAAB remaining.

Full current table (offseason pool, IR included; L mean 47,363.9, σ 3,623.5):

| Team | QB | RB | WR | TE | FLEX | L | rk | ω | Picks | Taxi | F | Frk | cuts/C | FAAB |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| DrewR87 | 6,544 | 13,077 | 20,327 | 3,803 | 10,500 | 52,418.8 | 1 | .60 | 40,931 | 4,167 | 45,098 | 9 | 3/2,900 | $50 |
| NoahMoell | 5,382 | 10,311 | 19,947 | 5,586 | 11,812 | 51,546.0 | 2 | .65 | 31,878 | 3,317 | 35,195 | 11 | 3/2,764 | $50 |
| cmgaither43 | 6,181 | 12,201 | 17,953 | 8,376 | 8,959 | 50,970.9 | 3 | .60 | 42,730 | 4,472 | 47,202 | 7 | 3/2,138 | $0 |
| joeydavis299 | 4,048 | 10,554 | 23,854 | 6,648 | 8,397 | 50,491.1 | 4 | .60 | 38,034 | 7,750 | 45,784 | 8 | 4/3,953 | $50 |
| **bengramling** | **5,744** | **15,434** | **13,718** | **5,195** | **11,741** | **49,598.8** | **5** | **.60** | **41,153** | **7,433** | **48,586** | **4** | **3/1,401** | **$50** |
| jaketoppen | 4,038 | 15,143 | 14,041 | 7,615 | 9,040 | 47,214.1 | 6 | .70 | 38,165 | 0 | 38,165 | 10 | **0/0** | $0 |
| trdouglas | 5,480 | 16,718 | 12,971 | 6,460 | 7,213 | 46,552.0 | 7 | .50 | 51,072 | 4,742 | 55,814 | 1 | 6/6,379 | $50 |
| ronakpatel32 | 6,256 | 8,459 | 18,660 | 4,313 | 9,874 | 46,217.9 | 8 | .35 | 31,242 | 0 | 31,242 | 12 | **0/0** | $45 |
| millj | 5,412 | 11,661 | 16,234 | 5,455 | 9,299 | 45,926.6 | 9 | .55 | 41,181 | 9,890 | 51,071 | 3 | 6/6,571 | $0 |
| josbaski | 4,937 | 13,029 | 20,508 | 3,263 | 6,543 | 44,975.3 | 10 | .40 | 47,522 | 7,246 | 54,768 | 2 | 2/1,034 | $44 |
| Jukinski | 5,707 | 7,707 | 18,712 | 3,888 | 7,607 | 42,140.3 | 11 | .35 | 44,453 | 4,031 | 48,484 | 5 | 4/5,073 | $50 |
| vishan | 7,663 | 7,648 | 14,148 | 5,123 | 6,712 | 40,315.7 | 12 | .25 | 45,290 | 2,365 | 47,655 | 6 | 2/3,560 | $50 |

This table also feeds `rank_L` → the 2027 pick-band projection (§3.2) and the ω auto-refresh (§5.2). Note the IR fix doing work: jaketoppen's offseason lineup counts Kittle (4,165, PUP) and Daniel Jones — L rank 6, not 7 — which is what a July lineup projection should say about healthy-next-season reserves.

---

## 9. Edge cases

**9.1 QB2 / depth in 1QB (Burrow insurance).** Depth value is exactly the insurance term `q_P·(ṽ(backup) − alternative)`. Flacco contributes only `0.06·919 ≈ 55` expected points, and keeping him is worth **−38.6** lineup points versus streaming (FA pool `R_QB = 1,562 > 919`) — the model concludes, correctly, that Flacco is worse than free insurance, and never spends trade capital on a QB2. Anthony Richardson (2,178) as the new QB2 is worth `ΔL = 0.06·(2178−919) = +75.5` — a real but small number (33 valued FA QBs; QB12 scored 18.7 ppw in this league's own 2025 data). Taxi'd Cam Ward (4,432) is **not** QB insurance — taxi players are lineup-ineligible; he lives in `F(T)` until promoted (§9.3).

**9.2 FLEX competition across RB/WR/TE.** Handled endogenously by the solver: my flexes are currently RB3/RB4 (Walker 6,281, Javonte 5,460), so a new WR enters my lineup above Evans 4,125 (WR3 bar) while a new RB must clear 5,460 (flex bar) — different marginal bars per position, per team, recomputed every snapshot. No positional weight table exists anywhere in the system.

**9.3 Taxi promotion timing (locks week 4).** Promotion is a transaction: `PromoScore(a) = Score(promote a [+ attached drop if actives full]) − 1[week > 4]·τ_lock`, with `τ_lock = 400` charging the permanently dead taxi slot after the week-4 lock (before the lock the freed slot can be refilled — it even absorbs a draft-day rookie, so promotion does not worsen the crunch). Cam Ward today: `ΔL = 0.06·(4432−919) = +210.8 → ω·ΔL = +126.5` against a free drop — marginally positive; the UI notes it burns Ward's taxi year and recommends holding until Burrow insurance actually matters (week 1).

**9.4 2-IR usage.** IR eligibility is strictly game-status OUT; 2 slots; IR players are active-cap-exempt (excluded from `Act(T)` and the crunch). In-season they leave `pool(T)`; offseason they stay in it (stale July tags must not gate lineup projections — Kittle, Charbonnet). Whenever a claim needs a roster spot and an active player is OUT with an IR slot free, recommend the IR move before any drop. Offseason: game statuses don't exist; the engine never suggests IR before week 1.

**9.5 Offseason vs in-season need signals.** One formula, one mode flag. Offseason: `u(a) = 1` everywhere, `L` is structural, crunch anchored to Aug 15, offseason bids. In-season: `u(a)` = 1.0 (healthy/questionable), 0.6 (OUT, expected return ≤ 3 weeks per KTC `injuryReturn`), 0.25 (OUT long-term/PUP), applied in the lineup solver only — `A(T)` always uses full `v` (availability is never a value override, so locked decision 1 holds). An injured starter automatically opens a ΔL hole that waiver/trade targets get credit for filling; streaming value emerges without a separate model.

**9.6 The unvalued player.** `v = 0`, never imputed (KTC's 500-asset floor means anyone missing is below churn level). Waller: RV = 0.0 → permanent top drop candidate; UI badge `unvalued`; an alert fires if any previously-valued rostered player falls out of KTC coverage (stale-crosswalk guard).

**9.7 Pick 1.01: concrete vs tranche, hold vs sell.** `P(1.01) = board(1) = 7,762` — the known 1.01 is worth +1,519 over the generic Early-1st tranche (6,243) the market anchors on; `SellFloor = 7,762`. Hold-vs-sell is now-credit- and crunch-aware: today, with 3 forced cuts pending, selling the 1.01 at full concrete price scores **+212.6** (crunch relief 1,056.4 slightly outruns the lost now-credit 843.8) — but after the recommended body-shedding trades execute (cuts → 1), the same sale scores **−860.5**: *sell bodies first, then hold the 1.01.* The engine sequences this itself because every proposal is scored against the current state.

**9.8 Roster crunch from the incoming draft class.** §4: 4 rookies in, 1 free taxi slot ⇒ 3 drops (Waller/Flacco/Diggs, 1,400.9). The marginal-hold view prices each pick net of its forced cut: the **4.01 is a liability** — `RV(4.01) = −287.6` — and e.g. swapping it for a 2028 Mid 4th scores **+991.2**. Shop late current-year picks to the zero-crunch teams (jaketoppen, ronakpatel32).

---

## 10. Parameters

| Parameter | Default | UI-tunable? | Where |
|---|---|---|---|
| `ω_me` win-now weight | **0.60** | **Yes — headline slider** | §5.2 |
| Opponent ω seeds (12 values) | table §5.2 | Yes (per-team) | §5.2 |
| ω auto-refresh coefficients | 0.25 / 0.45 / 0.05, clamp [0.20, 0.75] | No (suggestion only) | §5.2 |
| ω in-season ramp / fade | +0.15·w/11 / −0.10 | Advanced | §5.2 |
| `q_QB,q_RB,q_WR,q_TE,q_FLEX` | .06/.14/.11/.10/.12 | Advanced | §2.2 |
| `R_P` rule | 3rd-best non-rookie FA, per snapshot | No (rule) | §2.3 |
| Availability `u` table | 1.0 / 0.6 / 0.25 | Advanced | §9.5 |
| `ρ_rook` rookie readiness | 0.50 | Advanced | §3.3 |
| Pick regimes | 2026 concrete `board(n)` (+`SellFloor = max(board, tranche)`); 2027 band by origin `rank_L` (9–12 E, 5–8 M, 1–4 L); 2028 flat Mid | No | §3.2 |
| Crunch event calendar | Aug-15 rookie draft; C = 0 after resolution | No | §4 |
| AdjV consolidation coefficients | (1.00, 0.90, 0.80) | No | §7.2 |
| Fairness band `ε_rel` / `ε_abs` | 20% / 500 (on AdjV) | Yes | §7.2 |
| Anti-fleece raw-sum ratio | 1.35 | No | §7.2 |
| `G_min` my-side floor / their floor | 150 / 0 | Yes | §7.2 |
| Tier A threshold / posture-fit cutoffs | 300 / ω ≥ .55 contender, ≤ .40 rebuilder | No | §7.4 |
| Mutual-benefit weight | 0.30 | Advanced | §7.3 |
| Max package size / give-list size | 3 per side / 8 + picks | Yes / Advanced | §7.1 |
| Anchor-ask markup | +8% | Advanced | §7.4 |
| DIP threshold | −6% vs trailing-30-day max | Yes | §7.6 |
| `N_min` claim threshold | 250 (on raw NetClaim) | Yes | §6.1 |
| `DROP_FLOOR` confirm bar | RV⁰ > 2,500 | Yes | §6.2 |
| Rival-demand ΔL threshold | 300 | Advanced | §6.3 |
| κ (KTC pts per $) | 25 | No | §6.4 |
| `k_need` | 6,000 (refit each January per §6.4) | Advanced | §6.4 |
| `g(D)` contest multipliers | 0.5 / 1.0 / 1.15 | Advanced | §6.4 |
| In-season bid clamp | 0.65 · B_rem | Yes | §6.4 |
| Offseason bid ladder | $0 / $1 @ D≥1 / min($3, 6%) @ D≥2 | Yes | §6.4 |
| Stash-only bid cap | $3 | Yes | §6.4 |
| `τ_lock` taxi-slot cost | 400 (after week 4) | Advanced | §9.3 |
| Rookie-FA exclusion | while draft `pre_draft` | No | §6.1 |

---

## 11. Worked examples (real 2026-07-26 data; all numbers reproduced by the reference implementation)

### 11.1 Waiver pickup with bid

**Claim Greg Dulcich (TE, MIA, KTC 2,662) — drop Darren Waller — bid $0** (offseason mode, free-option claim).

```
CLAIM Greg Dulcich (TE)                                    NetClaim 0.0 · raw +1,064.8
  Lineup  ω·ΔΛ:     +0       LaPorta 5,195 holds TE; Theo Johnson 2,673 keeps
                             the TE backup rung by 11 points
  Wealth  (1−ω)·ΔA: +1,064.8   0.40 × 2,662 (Waller out at v = 0)
  Crunch  −ΔC:      −1,064.8   Dulcich lands below the Aug-15 cut line — he
                             becomes scheduled cut #3 (cuts stay 3/3)
  Verdict: FREE OPTION — claim at $0. Strictly better doomed inventory; the
  +1,065 becomes real only if a body-shedding trade lands before Aug 15 (§11.2
  does exactly that). Bid $0: rival demand D = 0 (no team has ΔL ≥ 300; three
  rivals hold $0 FAAB until the ~Aug-12 reset).
QUEUED (post-draft): add Anthony Richardson / drop Joe Flacco — the only
  ΔL > 0 claim on the board (+75.5 QB2 insurance): −22.7 today, ≈ +549 once
  the draft resolves and the crunch clears.
```

In-season mode reference (same pipeline, 2025 backtests): TE-hole emergency, ΔL ≈ 2,000, B_rem $190, D = 1 → `min(190·2000/6000, …, 0.65·190)` = **$63** (actual 2025 winning bid: $60). QB1 playoff stream, ΔL ≈ 3,500, B_rem $200 → **$117** (actual: $115).

### 11.2 Trade with a named team — jaketoppen (defending champ)

Counterparty facts the generator keyed on: WR starter group ranks 10th (WR3 = Malik Washington 3,203; backup Mooney 2,489), ω = 0.70 (bought Gibbs, DJ Moore, Pacheco inside 12 months), **zero crunch** (18 actives, 3 free taxi slots — one of only two teams that can absorb bodies), pick-rich in 2027 (own 1st, vishan's 1st, Jukinski's 2nd). I am the mirror image: WR-heavy bench with no lineup role and 3 forced cuts pending.

**Send Courtland Sutton (WR, 3,674) + Mike Evans (WR, 4,125) → receive jaketoppen's own 2027 1st (origin rank_L 6 → Mid = 6,118).**

```
TRADE with jaketoppen (ω = 0.70, activity High)                    H = +773.6
  MY SIDE (ω = 0.60):                                          Score +595.1
    Lineup  ω·ΔL:    −150.0   WR3 Evans→Hunter −57.0 · WR backup
                              Hunter→Godwin (4,061→3,644) −137.6 ·
                              FLEX backup Hunter→Dowdle −55.4
    Rookie credit:   +16.6    ω·ΔNC +27.7 — virtual Love (1.01) already
                              restores the FLEX-backup rung
    Wealth (1−ω)·ΔA: −672.4   0.40 × (6,118 − 7,799)
    Crunch −ΔC:    +1,400.9   cuts 3 → 1: Flacco + Diggs cuts rescued
  THEIR SIDE (ω = 0.70):                                       Score +1,401.8
    Lineup  ω·ΔL:    +897.5   WR3 Washington→Evans +820.6 · WR backup
                              Mooney→Sutton +391.1 · FLEX backup
                              Mason→Sutton +70.6  (ΔL = +1,282.2)
    Wealth (1−ω)·ΔA: +504.3   0.30 × 1,681
    Crunch −ΔC:          ±0   0 cuts before and after (20 actives → 1 vet
                              to taxi, legal pre-lock)
  FILTERS  AdjV 4,125 + 0.90·3,674 = 7,431.6 vs 6,118 → gap 17.7% ≤ 20% ✓
           raw ratio 7,799/6,118 = 1.27 < 1.35 ✓ · legality ✓ · floors ✓
  TIER A   contender-fit ✓ (ΔL +1,282 — he's buying lineup, precedent: paid
           2027 2nds for DJ Moore and Goff+Jones) · anchor ask ≈ +8%
  ω-SENSITIVITY (me): 0.5 → +809 · 0.6 → +595 · 0.7 → +381  (robust)
```

The blend and the crunch doing their jobs together: I give up ~222 points of expected lineup value (net of rookie credit), bank a 2027 1st from my aging WR surplus, and rescue 1,400.9 of forced-cut value — while the champ upgrades three WR rungs from a pick stockpile at zero roster cost. Runner-up surfaced the same run: **Diggs → jaketoppen for their own 2027 4th (2,036): me +814.4 / them +216.6** (almost pure crunch arbitrage — Diggs's crunch-aware RV is 0). After either executes, the whole tab re-scores (§7.1); notably the 1.01 flips to a firm hold (§9.7).

### 11.3 League-tab row

```
what would it take (bengramling)          ω 0.60 · L 49,598.8 (5th, z +0.62)
  LINEUP   QB 5,744 (5th)   RB 15,434 (2nd)   WR 13,718 (11th)
           TE 5,195 (7th)   FLEX 11,741 (2nd)
           read: elite RB room carries both flexes; WR is the hole (WR3 =
           Mike Evans 4,125, age 32); QB set (Burrow), TE league-average
  FUTURE   Picks 41,153 — 2026 concrete 15,847 (1.01→7,762 · 2.09→3,236 ·
           3.03→2,927 · 4.01→1,922) · 2027 own Mid R1/R2/R4 12,293 ·
           2028 Mid set 13,013
           Taxi 7,433 — Cam Ward 4,432 · Elijah Arroyo 3,001
           F = 48,586 (4th)
  MARKET   crunch 3 cuts / 1,400.9 (Waller · Flacco · Diggs, due Aug 15)
           FAAB $50/50
```

Contrast rows the user reads off the same table: trdouglas F = 55,814 (1st, pick hoard) but 6 forced cuts (motivated seller); jaketoppen taxi = 0, WR 14,041 (10th), **0 cuts** (the league's natural buyer — exactly why §11.2 targets him); ronakpatel32 F = 31,242 (12th, zero taxi, 0 cuts).

---

## 12. Explainability contract

Every recommendation carries a decomposition object; the UI renders the indented blocks in §11 from this schema (never hand-written). `dL_terms` are produced by **diffing the before/after slot assignments and backups from the same solver call that scored the move** — the explanation can never disagree with the number. Every ΔL is click-expandable to the two 9-row before/after lineup tables (the full audit trail, cheap to render).

```json
{
  "action": "TRADE",
  "counterparty": "jaketoppen",
  "give": [{"type": "player", "name": "Courtland Sutton", "v": 3674},
           {"type": "player", "name": "Mike Evans", "v": 4125}],
  "get":  [{"type": "pick", "name": "2027 R1 (own)", "v": 6118, "mv": 6118,
            "pricing": {"rule": "tranche", "band": "Mid", "band_reason": "jaketoppen rank_L 6"}}],
  "sides": {
    "me":   {"omega": 0.60, "dL": -250.0, "dNC": 27.7, "dA": -1681.0, "dC": -1400.9, "score": 595.1,
             "dL_terms": [
               {"kind": "starter", "slot": "WR3",  "out": "Mike Evans 4125",   "in": "Travis Hunter 4061", "delta": -57.0},
               {"kind": "backup",  "slot": "WR",   "out": "Travis Hunter 4061","in": "Chris Godwin 3644",  "delta": -137.6},
               {"kind": "backup",  "slot": "FLEX", "out": "Travis Hunter 4061","in": "Rico Dowdle 3830",   "delta": -55.4}],
             "crunch": {"cuts_before": 3, "cuts_after": 1, "rescued": ["Joe Flacco", "Stefon Diggs"]}},
    "them": {"omega": 0.70, "dL": 1282.2, "dNC": 0.0, "dA": 1681.0, "dC": 0.0, "score": 1401.8,
             "dL_terms": [
               {"kind": "starter", "slot": "WR3",  "out": "Malik Washington 3203", "in": "Mike Evans 4125",      "delta": 820.6},
               {"kind": "backup",  "slot": "WR",   "out": "Darnell Mooney 2489",   "in": "Courtland Sutton 3674","delta": 391.1},
               {"kind": "backup",  "slot": "FLEX", "out": "Jordan Mason 3380",     "in": "Courtland Sutton 3674","delta": 70.6}]}
  },
  "fairness": {"adj": "7431.6 vs 6118 (gap 17.7%, band 20%)", "raw_ratio": 1.27, "cap": 1.35},
  "tier": "A", "posture_fit": true, "activity": "High", "anchor_ask_pct": 8,
  "omega_sensitivity": {"0.5": 809.1, "0.6": 595.1, "0.7": 381.1},
  "audit": {"lineup_tables": "before/after 9-row pairs, per side"},
  "rank_score_H": 773.6
}
```

CLAIM/DROP/PROMOTE use the same schema with a `bid` block (`{mode, D, netclaim, netclaim_raw, ceiling, clamp, bid}`) and the same crunch line. Rule: **every number shown is reproducible from §§2–7 — no unexplained adjustments, and displayed components must sum to the score.**

---

## 13. Implementation invariants (tests an engineer must ship)

1. **Solver ground truth:** the lineup solver on 2025 weekly data reproduces Sleeper `ppts` exactly for all 12 rosters (known-good fixture from `production-baselines-2025.md` §7).
2. **Crosswalk fixtures:** roster-4 position sums equal the published table (RB = 34,349); `taxi ⊆ players`, `reserve ⊆ players`; unvalued-player count = 1 (Waller ⇒ `v = 0`, no throw; alert if it grows).
3. **Lineup fixtures (2026-07-26):** `L(me) = 49,598.8`; full 12-row L table of §8; offseason pool includes IR (jaketoppen L = 47,214.1 with Kittle/Jones counted).
4. **Need invariants:** `L(T ∪ a) ≥ L(T)`; `VTT`, `RV` monotone in `v` holding roster fixed; synthetic 5555 pair → WR > QB; **real same-K pair** Jameson Williams / Jaxson Dart (both 5,408) → VTT 2,870.2 > 2,324.8 on roster 4.
5. **Pick fixtures:** `P(1.01) = 7,762`, `P(2.09) = 3,236`, `SellFloor(2.09) = 3,504`; `F(trdouglas) = 55,814`, `F(me) = 48,586`; all 48 × {2026, 2027} + 48 own 2028 picks price without error; missing board ranks interpolate.
6. **Crunch fixtures:** cuts vector = (cmg 3, jake 0, Jukinski 4, me 3, trdouglas 6, millj 6, joey 4, vishan 2, josbaski 2, Noah 3, Drew 3, ronak 0); `C(me) = 1,400.9` with cut set {Waller, Flacco, Diggs}; `C` recomputed on every post-transaction roster (add+drop swap of Waller→Dulcich yields ΔC = +1,064.8, NetClaim ≈ 0 — the free-option invariant); `C = 0` for all teams after draft-status flips to complete.
7. **Bid backtests:** Waller 2025-wk4 fixture → $63 (actual $60); Kyler 2025-wk11 → $117 (actual $115); offseason board today → all $0.
8. **Explanation = computation:** rendered `dL_terms` are generated by diffing the scoring solver's own before/after assignments; component sums must equal the score to 0.1.
9. **Scrape guards:** assert 480–520 KTC assets with `oneQBValues.value` present; 36-RDP set re-verified; crosswalk re-joined with alerts on unmapped `playerID`; `R_P`, tranche list, rookie board re-derived each snapshot; daily value archive appended (DIP flag depends on it).
10. **Bounds (erratum 8):** trade enumeration ≤ 3 assets/side from give-lists (8 + scheduled cuts + picks) per pair — a few 10⁶ enumerated packages league-wide, all passed through the cheap §7.2 pre-filters. Full joint evaluation of every pre-filter survivor is minutes, not sub-second (each evaluation is two lineup solves plus one crunch recompute), so joint scoring is **budgeted per (give-size × get-size) bucket, best-first by an additive proxy corrected for the §4 multi-cut interaction** (`trade_eval_cap_per_bucket = 250` ⇒ ~10⁴ joint evaluations; full recompute of every tab in single-digit seconds). The §11.2 pinned candidates must survive the budget (tested); the stratified buckets keep 1×1/2×1 bread-and-butter deals evaluated alongside 3×3 consolidations.

---

## Errata (2026-07-26 implementation review)

The reference implementation exposed places where this spec's formula prose contradicted its own pinned tables (§§2.4–2.5, 4, 6.1, 8, 11). In every case the pinned numbers are the contract; the prose above has been corrected in place and each correction is marked with an erratum number:

1. **§6.1 NetClaim** is scored against the single standing drop (head of the §6.2 RV queue), not a max over legal drops — the original "max over legal drops d" formula contradicted the board's own pinned Richardson −45.8 (best-drop would give −22.7 via Flacco).
2. **§7.1 give-list** protects the top-2 assets by raw `v` and appends scheduled cuts beyond the 8 — literal "8 highest by σ⁰" would rank Jeanty (2,625.1) and Hampton (2,589.2) first, contradicting the section's own quoted list (Walker 2,486 first).
3. **§7.2 filter 1** exempts all-scheduled-cut packages from the fairness band — the pinned §11.2 runner-up (Diggs 2,641 → 2027 4th 2,036) violates the band (gap 605 > 528.2) and is intended.
4. **§7.3 ranking** is acceptance-tier first, then `H` within tier (the original text implied pure `H` order).
5. **§7.4 posture-fit letter:** contender-fit tests the largest-`mv` asset in the package the contender receives (not the deal-wide largest-`v` player); rebuilder future share is measured against raw `Σ mv` (not `AdjV`).
6. **§7.6 SellFloor** is a card flag (`below_sell_floor`), not a filter — §9.8's pinned recommendation itself sells the 4.01 below its floor.
7. **§2.3 replacement anchors** exclude KTC rookie-flagged FAs unconditionally (matching §10's "3rd-best non-rookie FA"), not only while the draft is `pre_draft`.
8. **§13.10 bounds** under-estimated joint-evaluation cost: full joint scoring of every pre-filter survivor is minutes, not sub-second. Joint evaluation is budgeted per size bucket, proxy best-first (250/bucket); the proxy adds back the §4 multi-cut interaction that a purely additive proxy misses (without it, the budget demonstrably buried candidates that outrank emitted ones — e.g. the same Sutton+Evans body-shed returning 2027 E2 + 2028 M1 = 9,731 raw inside all bands).

### Taxi economics (2026-07-26 reviewer finding + house-rule clarification)

House rules confirmed by the league owner: taxi is stashable only by 1st/2nd-year
players, fillable only until the lock **after week 4** (`taxi_deadline = 4`),
promote-out any time; a vacated slot cannot be refilled post-lock.

9. **§3.1/§5 wealth debit (BUG FIX):** `apply_tx` debited departures from the
   lineup pool only, so a traded-away TAXI player's value was never removed from
   `W` (both sides of a taxi-for-taxi swap showed positive `ΔW`, violating the
   zero-sum invariant), his value stayed in `F`, and his slot never freed.
   Departures now debit full `v` wherever the player lives; the freed slot
   increments `free_taxi` pre-lock only (post-lock it is dead capacity, matching
   the §9.3 lock economics). The nightly board never tripped this (give-lists
   exclude taxi); only explicit proposals (`scripts/score_trade.py`) did.
10. **Incoming stash routing:** pre-lock, an acquired taxi-eligible player
    (`seasonsExperience ≤ 1`) who would not crack the starting lineup routes to a
    **surplus** free taxi slot — no active spot, no attached drop, no crunch.
    Slots already earmarked as crunch absorption (`taxi_slot_demand` = active
    overflow incl. incoming current-year picks) are never consumed: stashing into
    them would trade a ~free drop for a forced cut (measured −114.5 vs ≈0 on
    today's board). Post-lock every arrival is active.
11. **Taxi insurance (`taxi_insurance_mult`, default 0.0 = OFF):** stashed players
    can count as discounted backup insurance in §2.2 via shadow entries
    (`sid + ":taxi"`, `v × mult`) in the lineup pool — a shadow outranking a
    starter models "would promote him". OFF by default because enabling it moves
    every pinned `L` in this document; flipping the default must ship together
    with a regeneration of the §2.4/§8/§11 tables.
12. **Empty-slot nudge:** pre-lock, the waiver board reports `taxi_fill` — the
    top stashable FAs for any SURPLUS free taxi slot. An empty slot at the lock
    is worth exactly zero; a locked stash is a free option.

This spec is the synthesis of a four-design judged panel (lenses: formal marginal-value, market-shark, minimal-model, mechanism-design). The winning architecture is Design A — the q-weighted insurance lineup model, the ω blend, `R_P` replacement anchors, and the explanation-equals-computation contract — with every judge-identified defect fixed: IR players now count in the offseason lineup pool, 2026 picks price at concrete board value (tranches demoted to the perception layer and sell floors), the 1.01 carries a readiness-discounted now-credit, and the in-season bid refit is fully specified. The highest-value grafts: Design D's roster-crunch shadow cost `C(T)` (implemented correctly — recomputed on every post-transaction roster, which turns July's waiver board into free-option claims and makes the 4.01-as-liability and sell-bodies-to-jaketoppen/ronakpatel32 conclusions fall out of the math) plus its trade-zone diagnostic and the real same-K test pair; Design B's market-realism layer (behavior-seeded opponent ω, AdjV consolidation coefficients, the 1.35 anti-fleece cap, posture-fit acceptance tiers, anchor asks, the DIP flag, and the 1.01 pick-anchor arbitrage); and Design C's calibrated in-season bid formula with its two 2025 backtests, the 0.65 budget clamp, the ω-sensitivity readout, and the before/after lineup tables as the universal audit artifact.