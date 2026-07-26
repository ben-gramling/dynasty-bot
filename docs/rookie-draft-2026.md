# Addendum: 2026 Rookie Draft Order Verification + KTC Rookie Board (Concrete Pick-Slot Pricing)

Research date: 2026-07-26. Sources: Sleeper API draft endpoints (fetched live) and `/home/bgram/dev/dynasty-bot/data/ktc_raw.json` (KTC scrape of 2026-07-26, `_meta.extracted_at = "2026-07-26"`, 500 assets, source `https://keeptradecut.com/dynasty-rankings`). Fetched JSON saved to scratchpad: `draft26.json`, `draft26_traded_picks.json`, plus derived `rookie_board_2026.json`.

## 1. Draft metadata — VERIFIED (resolves the "unverified pre-draft" flag)

`GET https://api.sleeper.app/v1/draft/1327016687945392128` returns **fully populated** `draft_order` (12 users) and `slot_to_roster_id` (all 12 slots) even though `status = "pre_draft"`. The API-document concern is resolved: both maps are populated pre-draft for this league; the scoring system can rely on them.

Key fields confirmed:

| Field | Value |
|---|---|
| draft_id | 1327016687945392128 |
| league_id | 1312124603224555520 (2026 Chicago Dynasty) |
| season / sport | 2026 / nfl |
| status | **pre_draft** |
| type | **linear** (`reversal_round: 0` — same slot order all 4 rounds, no snake) |
| settings.rounds | **4** (48 total picks) |
| settings.player_type | **1** (rookies-only draft) |
| settings.teams | 12 |
| start_time | 1786806059000 = 2026-08-15 15:00:59 UTC |
| metadata.scoring_type | dynasty_ppr |
| cpu_autopick | 1; pick_timer 0 |

`draft_order` maps user `1095425159290331136` (bengramling) to **slot 1** — confirmed.

## 2. slot_to_roster_id — full 12-slot map, matches the claimed order exactly

Raw: `{"1":4,"2":8,"3":12,"4":3,"5":9,"6":1,"7":5,"8":10,"9":11,"10":7,"11":6,"12":2}`

Cross-checked three ways (slot → roster_id → roster owner_id from `rosters26.json` → display_name from `users26.json`, and independently slot → draft_order user). All 12 slots agree on both paths; the claimed order in the league document is correct on all 12 rows:

| Slot | roster_id | User (user_id) |
|---|---|---|
| 1 | 4 | bengramling (1095425159290331136) |
| 2 | 8 | vishan (1050975911891357696) |
| 3 | 12 | ronakpatel32 (1051305245869064192) |
| 4 | 3 | Jukinski (939924299933175808) |
| 5 | 9 | josbaski (731001489828503552) |
| 6 | 1 | cmgaither43 (964266240745226240) |
| 7 | 5 | trdouglas (996848070979629056) |
| 8 | 10 | NoahMoell (1251373941738450944) |
| 9 | 11 | DrewR87 (374691873518063616) |
| 10 | 7 | joeydavis299 (964266016853307392) |
| 11 | 6 | millj (964264771371487232) |
| 12 | 2 | jaketoppen (815026025661583360) |

## 3. Traded-picks reconciliation — draft-scoped view agrees with league-level view exactly

- `GET /v1/draft/1327016687945392128/traded_picks` → **24 rows**, all `season: "2026"`.
- League-level file `picks26.json` → **36 rows** = **24 rows season 2026 + 12 rows season 2027**. The 12-row difference is entirely the 2027 picks (no 2027 draft object exists yet, so they only appear at league level).
- Keyed on `(season, round, roster_id)`: the 24 draft-scoped rows and the 24 league-level 2026 rows have **identical key sets and identical `owner_id`/`previous_owner_id` on every row** — zero mismatches. Both endpoints are current-final-ownership views (one row per traded pick, no chain duplicates). The pick-ownership table in the league document is confirmed.

### Concrete 2026 pick grid (linear ⇒ overall pick = (round−1)×12 + slot; owner after applying the 24 trades)

| Pick | Overall | Original roster | Current owner |
|---|---|---|---|
| 1.01 | 1 | 4 bengramling | **4 bengramling** |
| 1.02 | 2 | 8 vishan | 8 vishan |
| 1.03 | 3 | 12 ronakpatel32 | 6 millj (traded) |
| 1.04 | 4 | 3 Jukinski | 1 cmgaither43 (traded) |
| 1.05 | 5 | 9 josbaski | 9 josbaski |
| 1.06 | 6 | 1 cmgaither43 | 3 Jukinski (traded) |
| 1.07 | 7 | 5 trdouglas | 5 trdouglas |
| 1.08 | 8 | 10 NoahMoell | 5 trdouglas (traded) |
| 1.09 | 9 | 11 DrewR87 | 11 DrewR87 |
| 1.10 | 10 | 7 joeydavis299 | 7 joeydavis299 |
| 1.11 | 11 | 6 millj | 11 DrewR87 (traded) |
| 1.12 | 12 | 2 jaketoppen | 3 Jukinski (traded) |
| 2.01 | 13 | 4 bengramling | 6 millj (traded) |
| 2.02 | 14 | 8 vishan | 8 vishan |
| 2.03 | 15 | 12 ronakpatel32 | 12 ronakpatel32 |
| 2.04 | 16 | 3 Jukinski | 3 Jukinski |
| 2.05 | 17 | 9 josbaski | 9 josbaski |
| 2.06 | 18 | 1 cmgaither43 | 5 trdouglas (traded) |
| 2.07 | 19 | 5 trdouglas | 5 trdouglas |
| 2.08 | 20 | 10 NoahMoell | 10 NoahMoell |
| 2.09 | 21 | 11 DrewR87 | **4 bengramling** (traded) |
| 2.10 | 22 | 7 joeydavis299 | 7 joeydavis299 |
| 2.11 | 23 | 6 millj | 1 cmgaither43 (traded) |
| 2.12 | 24 | 2 jaketoppen | 2 jaketoppen |
| 3.01 | 25 | 4 bengramling | 1 cmgaither43 (traded) |
| 3.02 | 26 | 8 vishan | 8 vishan |
| 3.03 | 27 | 12 ronakpatel32 | **4 bengramling** (traded) |
| 3.04 | 28 | 3 Jukinski | 6 millj (traded) |
| 3.05 | 29 | 9 josbaski | 9 josbaski |
| 3.06 | 30 | 1 cmgaither43 | 6 millj (traded) |
| 3.07 | 31 | 5 trdouglas | 1 cmgaither43 (traded) |
| 3.08 | 32 | 10 NoahMoell | 10 NoahMoell |
| 3.09 | 33 | 11 DrewR87 | 11 DrewR87 |
| 3.10 | 34 | 7 joeydavis299 | 7 joeydavis299 |
| 3.11 | 35 | 6 millj | 10 NoahMoell (traded) |
| 3.12 | 36 | 2 jaketoppen | 2 jaketoppen |
| 4.01 | 37 | 4 bengramling | **4 bengramling** |
| 4.02 | 38 | 8 vishan | 6 millj (traded) |
| 4.03 | 39 | 12 ronakpatel32 | 6 millj (traded) |
| 4.04 | 40 | 3 Jukinski | 3 Jukinski |
| 4.05 | 41 | 9 josbaski | 9 josbaski |
| 4.06 | 42 | 1 cmgaither43 | 12 ronakpatel32 (traded) |
| 4.07 | 43 | 5 trdouglas | 5 trdouglas |
| 4.08 | 44 | 10 NoahMoell | 10 NoahMoell |
| 4.09 | 45 | 11 DrewR87 | 8 vishan (traded) |
| 4.10 | 46 | 7 joeydavis299 | 7 joeydavis299 |
| 4.11 | 47 | 6 millj | 5 trdouglas (traded) |
| 4.12 | 48 | 2 jaketoppen | 10 NoahMoell (traded) |

**The user (bengramling, roster 4) owns exactly 4 picks: 1.01 (overall 1), 2.09 (overall 21), 3.03 (overall 27), 4.01 (overall 37).** His own 2.01 and 3.01 are traded away (to millj and cmgaither43 respectively).

## 4. KTC 2026 rookie board — all 59 `rookie: true` records, sorted by `oneQBValues.value`

All 59 have `draftYear: 2026`; no other asset in the file has `draftYear: 2026`. Age `-1.0` in the raw file means unpublished (shown as “–”). NFL team codes are KTC’s (NOS=NO, LVR=LV, KCC=KC, TBB=TB, SFO=SF, NEP=NE, JAC=JAX). `rookieRank` is KTC’s 1QB rookie rank; values **55, 57, 58, 59, 60 are absent** from the file (those rookies fell outside the 500-asset scrape), so the 59 records cover ranks 1–54, 56, 61–64. Sorting by 1QB value reproduces rookieRank order exactly (monotonic).

| # | rookieRank | Name | Pos | NFL | Age | 1QB value | 1QB overall rank |
|---|---|---|---|---|---|---|---|
| 1 | 1 | Jeremiyah Love | RB | ARI | 21.2 | **7762** | 10 |
| 2 | 2 | Carnell Tate | WR | TEN | 21.5 | 6428 | 27 |
| 3 | 3 | Jordyn Tyson | WR | NOS | 22.0 | 6011 | 43 |
| 4 | 4 | Makai Lemon | WR | PHI | 22.2 | 5652 | 53 |
| 5 | 5 | Jadarian Price | RB | SEA | 22.8 | 5504 | 62 |
| 6 | 6 | KC Concepcion | WR | CLE | 21.8 | 5133 | 75 |
| 7 | 7 | Kenyon Sadiq | TE | NYJ | 21.4 | 4767 | 84 |
| 8 | 8 | Fernando Mendoza | QB | LVR | 22.8 | 4703 | 88 |
| 9 | 9 | Omar Cooper Jr. | WR | NYJ | 22.6 | 4464 | 98 |
| 10 | 10 | Denzel Boston | WR | CLE | – | 4363 | 104 |
| 11 | 11 | Eli Stowers | TE | PHI | 23.3 | 4236 | 113 |
| 12 | 12 | Jonah Coleman | RB | DEN | 22.9 | 3874 | 133 |
| 13 | 13 | Chris Bell | WR | MIA | 22.1 | 3736 | 144 |
| 14 | 14 | Antonio Williams | WR | WAS | – | 3644 | 153 |
| 15 | 15 | Germie Bernard | WR | PIT | 22.6 | 3552 | 159 |
| 16 | 16 | Nicholas Singleton | RB | TEN | – | 3536 | 160 |
| 17 | 17 | Zachariah Branch | WR | ATL | – | 3336 | 175 |
| 18 | 18 | De'Zhaun Stribling | WR | SFO | 23.6 | 3290 | 180 |
| 19 | 19 | Malachi Fields | WR | NYG | – | 3277 | 182 |
| 20 | 20 | Elijah Sarratt | WR | BAL | – | 3274 | 183 |
| 21 | 21 | Ty Simpson | QB | LAR | 23.6 | 3236 | 189 |
| 22 | 22 | Kaytron Allen | RB | WAS | – | 3141 | 197 |
| 23 | 23 | Ted Hurst | WR | TBB | 22.1 | 3126 | 198 |
| 24 | 24 | Emmett Johnson | RB | KCC | – | 3117 | 201 |
| 25 | 25 | Chris Brazzell II | WR | CAR | – | 3072 | 205 |
| 26 | 26 | Skyler Bell | WR | BUF | 24.0 | 3068 | 207 |
| 27 | 27 | Ja'Kobi Lane | WR | BAL | – | 2927 | 214 |
| 28 | 28 | Mike Washington Jr. | RB | LVR | – | 2866 | 219 |
| 29 | 29 | Max Klare | TE | LAR | 23.0 | 2796 | 225 |
| 30 | 30 | Demond Claiborne | RB | MIN | – | 2469 | 262 |
| 31 | 31 | Kevin Coleman | WR | MIA | 22.9 | 2388 | 271 |
| 32 | 32 | Kaelon Black | RB | SFO | – | 2282 | 283 |
| 33 | 33 | Eli Raridon | TE | NEP | 22.4 | 2275 | 285 |
| 34 | 34 | Oscar Delp | TE | NOS | 23.0 | 2177 | 293 |
| 35 | 35 | Caleb Douglas | WR | MIA | 22.9 | 2170 | 295 |
| 36 | 36 | Justin Joly | TE | DEN | – | 1959 | 315 |
| 37 | 37 | Bryce Lance | WR | NOS | 23.9 | 1922 | 319 |
| 38 | 38 | Brenen Thompson | WR | LAC | 23.0 | 1870 | 326 |
| 39 | 39 | Eli Heidenreich | RB | PIT | 23.1 | 1816 | 331 |
| 40 | 40 | Zavion Thomas | WR | CHI | – | 1774 | 339 |
| 41 | 41 | Adam Randall | RB | BAL | – | 1611 | 360 |
| 42 | 42 | Garrett Nussmeier | QB | KCC | – | 1531 | 369 |
| 43 | 43 | Michael Trigg | TE | DAL | – | 1466 | 381 |
| 44 | 44 | Seth McGowan | RB | IND | 24.8 | 1460 | 384 |
| 45 | 45 | Deion Burks | WR | IND | – | 1288 | 403 |
| 46 | 46 | CJ Daniels | WR | LAR | 24.6 | 1286 | 405 |
| 47 | 47 | Cade Klubnik | QB | NYJ | – | 1237 | 413 |
| 48 | 48 | Cyrus Allen | WR | KCC | – | 1187 | 422 |
| 49 | 49 | J'Mari Taylor | RB | JAC | – | 1120 | 431 |
| 50 | 50 | Le'Veon Moss | RB | MIA | 23.7 | 1093 | 435 |
| 51 | 51 | Sam Roush | TE | CHI | 22.9 | 1032 | 442 |
| 52 | 52 | Barion Brown | WR | NOS | 22.6 | 1028 | 443 |
| 53 | 53 | Jam Miller | RB | NEP | – | 977 | 449 |
| 54 | 54 | Matthew Hibner | TE | BAL | – | 910 | 455 |
| 55 | 56 | Jack Endries | TE | CIN | – | 798 | 466 |
| 56 | 61 | Drew Allar | QB | PIT | – | 186 | 722 |
| 57 | 62 | Cole Payton | QB | PHI | 23.8 | 168 | 733 |
| 58 | 63 | Taylen Green | QB | CLE | 23.8 | 167 | 734 |
| 59 | 64 | Carson Beck | QB | ARI | 24.7 | 138 | 743 |

1QB-league caveat baked into the data: QB rookies collapse in 1QB values (Mendoza 4703 1QB vs 5472 SF; Klubnik 1237 vs 1939; Beck 138 vs 2585). Use `oneQBValues` exclusively for this league.

## 5. Value ladder: concrete slots vs generic 2026 tranche assets

KTC 2026 tranche values (RDP assets in the same file, 1QB): Early 1st **6243**, Mid 1st **5279**, Late 1st **4654**, Early 2nd **4067**, Mid 2nd **3630**, Late 2nd **3504**, Early 3rd 2835, Mid 3rd 2637, Late 3rd 2482, Early 4th 2033, Mid 4th 1892, Late 4th 1787. (2027: E1 7398, M1 6118, L1 5562, E2 4524, M2 4139, L2 3855. 2028: E1 5654, M1 5207, L1 4768, E2 3852, M2 3579, L2 3389 — note a 2027 1st > same-tier 2026 1st because the 2027 class is unknown/premium.)

### Rookie ranks 1–15 vs the 1st-round tranches (requested ladder)

| Rank | Rookie 1QB | Nearest tranche context |
|---|---|---|
| 1 | 7762 | +1519 over Early 1st (6243) — the 1.01 is worth ~24% more than the generic tranche |
| 2 | 6428 | +185 over Early 1st |
| 3 | 6011 | −232 under Early 1st; +732 over Mid 1st |
| 4 | 5652 | +373 over Mid 1st (5279) |
| 5 | 5504 | +225 over Mid 1st |
| 6 | 5133 | −146 under Mid 1st; +479 over Late 1st |
| 7 | 4767 | +113 over Late 1st (4654) |
| 8 | 4703 | +49 over Late 1st |
| 9 | 4464 | −190 under Late 1st; +397 over Early 2nd |
| 10 | 4363 | +296 over Early 2nd (4067) |
| 11 | 4236 | +169 over Early 2nd |
| 12 | 3874 | −193 under Early 2nd; +244 over Mid 2nd |
| 13 | 3736 | +106 over Mid 2nd (3630) |
| 14 | 3644 | +14 over Mid 2nd |
| 15 | 3552 | −78 under Mid 2nd; +48 over Late 2nd |

### Rookie ranks 13–24 vs the 2nd-round tranches (requested ladder)

| Rank | Rookie 1QB | vs Early 2nd 4067 | vs Mid 2nd 3630 | vs Late 2nd 3504 |
|---|---|---|---|---|
| 13 | 3736 | −331 | +106 | +232 |
| 14 | 3644 | −423 | +14 | +140 |
| 15 | 3552 | −515 | −78 | +48 |
| 16 | 3536 | −531 | −94 | +32 |
| 17 | 3336 | −731 | −294 | −168 |
| 18 | 3290 | −777 | −340 | −214 |
| 19 | 3277 | −790 | −353 | −227 |
| 20 | 3274 | −793 | −356 | −230 |
| 21 | 3236 | −831 | −394 | −268 |
| 22 | 3141 | −926 | −489 | −363 |
| 23 | 3126 | −941 | −504 | −378 |
| 24 | 3117 | −950 | −513 | −387 |

### Tranche vs slot-average summary (slot N ≈ rookie rank N under rational linear drafting)

| 2026 tranche (1QB) | Covers overall picks | Avg of rookie ranks in window | Tranche − slot-avg |
|---|---|---|---|
| Early 1st 6243 | 1–4 | 6463 | **−220** (only tranche below its slots — the 1.01 outlier drags the window up) |
| Mid 1st 5279 | 5–8 | 5027 | +252 |
| Late 1st 4654 | 9–12 | 4234 | +420 |
| Early 2nd 4067 | 13–16 | 3617 | +450 |
| Mid 2nd 3630 | 17–20 | 3294 | +336 |
| Late 2nd 3504 | 21–24 | 3155 | +349 |
| Early 3rd 2835 | 25–28 | 2983 | −148 |
| Mid 3rd 2637 | 29–32 | 2484 | +153 |
| Late 3rd 2482 | 33–36 | 2145 | +337 |
| Early 4th 2033 | 37–40 | 1846 | +187 |
| Mid 4th 1892 | 41–44 | 1517 | +375 |
| Late 4th 1787 | 45–48 | 1250 | +537 |

Design implication for slot→value interpolation: KTC generic tranches carry an **uncertainty/option premium** over the deterministic rank-N rookie almost everywhere (+150 to +537), EXCEPT at the very top where a known 1.01 (7762) is worth far more than "2026 Early 1st" (6243). A pick-slot pricer should therefore use `rookie_board[slot].oneQB_value` directly for concrete known slots (draft order is final — linear, all 48 slots resolved above), and reserve tranche values only for future-year picks (2027/2028) whose slot is unknown. Piecewise-linear interpolation over the rank→value curve is well-behaved: the curve is strictly decreasing with a steep head (7762→6428→6011), a plateau at ranks 17–24 (~3336→3117), and a long tail.

### Priced examples for the user's actual 2026 picks (bengramling, roster 4)

| Pick held | Overall | Rank-N rookie (today) | Concrete 1QB value | Generic tranche it falls in | Tranche value | Concrete − tranche |
|---|---|---|---|---|---|---|
| 1.01 | 1 | Jeremiyah Love RB | **7762** | 2026 Early 1st | 6243 | **+1519** |
| 2.09 | 21 | Ty Simpson QB | 3236 | 2026 Late 2nd | 3504 | −268 |
| 3.03 | 27 | Ja'Kobi Lane WR | 2927 | 2026 Early 3rd | 2835 | +92 |
| 4.01 | 37 | Bryce Lance WR | 1922 | 2026 Early 4th | 2033 | −111 |

Net: pricing the user's picks concretely instead of by tranche adds ~+1232 total, nearly all from the 1.01. Note the 2.09 caveat: rank-21 today is a QB (Simpson), which a 1QB-league drafter at pick 21 might skip — a slot pricer may want max(rank-N value, next-best-non-QB value) as a refinement; rank-22 non-QB is Kaytron Allen RB 3141 (−363 vs tranche, similar conclusion).

## 6. File references

- `/tmp/claude-1000/-home-bgram-dev-dynasty-bot/9d23798c-22b9-434a-b902-71d156ef37bd/scratchpad/draft26.json` — draft metadata (fetched this session)
- `/tmp/claude-1000/-home-bgram-dev-dynasty-bot/9d23798c-22b9-434a-b902-71d156ef37bd/scratchpad/draft26_traded_picks.json` — 24 draft-scoped traded picks (fetched this session)
- `/tmp/claude-1000/-home-bgram-dev-dynasty-bot/9d23798c-22b9-434a-b902-71d156ef37bd/scratchpad/picks26.json` — league-level 36-row pick file (pre-existing; reconciled)
- `/tmp/claude-1000/-home-bgram-dev-dynasty-bot/9d23798c-22b9-434a-b902-71d156ef37bd/scratchpad/rookie_board_2026.json` — derived 59-row rookie board extract
- `/home/bgram/dev/dynasty-bot/data/ktc_raw.json` — KTC source (500 assets, 59 rookies, 36 RDP tranche assets)