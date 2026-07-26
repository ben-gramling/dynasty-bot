# KTC ↔ Sleeper Crosswalk, Roster KTC Totals, and Free-Agent Pool

**League:** Chicago Dynasty (Sleeper league_id `1312124603224555520`, 2026 season, 12 teams, 1QB, status pre_draft)
**Built:** 2026-07-26
**Inputs:** Sleeper player dump (`players_nfl.json`, 12,201 players), 2026 rosters (`rosters26.json`, 12 rosters), KTC scrape (`/home/bgram/dev/dynasty-bot/data/ktc_raw.json`, 500 assets scraped 2026-07-26, values "updated 4 minutes ago" at scrape time)
**Output artifact:** crosswalk saved to **`/home/bgram/dev/dynasty-bot/data/ktc_sleeper_map.json`**

Because this is a 1QB league (no SUPER_FLEX slot), all values below use KTC's **`oneQBValues.value`**. Do **not** use `superflexValues` — the KTC site's default display is Superflex, but the raw JSON carries both.

**Headline result: all 464 KTC player records joined to a unique Sleeper player_id (100% match rate; 459/464 = 98.9% automatic, 5 manual overrides, 0 unresolved, 0 sleeper_id collisions).** The 36 `position='RDP'` draft-pick records were excluded as instructed.

---

## 1. KTC → Sleeper NFL team-code map

KTC and Sleeper agree on 24 of 32 team codes. The 8 differing codes plus the free-agent convention:

| KTC code | Sleeper code | Team |
|---|---|---|
| `GBP` | `GB` | Green Bay Packers |
| `JAC` | `JAX` | Jacksonville Jaguars |
| `KCC` | `KC` | Kansas City Chiefs |
| `LVR` | `LV` | Las Vegas Raiders |
| `NEP` | `NE` | New England Patriots |
| `NOS` | `NO` | New Orleans Saints |
| `SFO` | `SF` | San Francisco 49ers |
| `TBB` | `TB` | Tampa Bay Buccaneers |
| `FA` | `null` | Free agent (KTC uses string `'FA'`; Sleeper sets `team: null`) |

Identical in both systems: ARI, ATL, BAL, BUF, CAR, CHI, CIN, CLE, DAL, DEN, DET, HOU, IND, LAC, LAR, MIA, MIN, NYG, NYJ, PHI, PIT, SEA, TEN, WAS. (Sleeper's dump also contains a legacy `OAK` on some inactive players; no KTC record maps to it.)

This exact map is stored under `team_code_map_ktc_to_sleeper` in `ktc_sleeper_map.json`.

---

## 2. Join methodology and results

**Normalization:** lowercase → strip `. ' - ,` → drop trailing suffix tokens (Jr/Sr/II/III/IV/V) → concatenate. Sleeper's `search_full_name` is pre-lowercased/de-punctuated but does **not** strip suffixes, and Sleeper's own naming is inconsistent (it stores "Marvin Harrison" without Jr., but stores nickname forms like "Chig Okonkwo"), so normalization was applied to `full_name` on both sides rather than trusting `search_full_name`.

**Match key:** `(normalized_name, position)` against a Sleeper index built from `position` ∪ `fantasy_positions`, restricted to QB/RB/WR/TE. **Team was used only as a tiebreaker** (after KTC→Sleeper code translation), because team fields genuinely disagree for players who moved this offseason. Fallback tiebreaker: Sleeper `status == 'Active'`.

**Results (464 KTC players):**

| Match method | Count |
|---|---|
| Unique on name+position | 457 |
| Team tiebreak (duplicate name+position in Sleeper) | 2 |
| Manual override (name-variant, no auto hit) | 5 |
| **Total matched** | **464 / 464 (100%)** |
| Unresolved / ambiguous | 0 |
| Duplicate sleeper_id collisions | 0 |

### 2a. Manual overrides (the 5 auto-join failures)

All five are name-variant cases (KTC formal name vs Sleeper nickname, or vice versa). Stored under `manual_overrides` in the JSON.

| KTC playerID | KTC name (pos, team) | → Sleeper player_id | Sleeper name (pos, team) | Cause |
|---|---|---|---|---|
| `1032` | Kenneth Gainwell (RB, TBB) | `7567` | Kenny Gainwell (RB, TB) | Kenneth vs Kenny |
| `1320` | Chigoziem Okonkwo (TE, WAS) | `8210` | Chig Okonkwo (TE, WAS) | Chigoziem vs Chig |
| `533` | Gabriel Davis (WR, BUF) | `6943` | Gabe Davis (WR, null/FA) | Gabriel vs Gabe (+team disagreement) |
| `1186` | Bam Knight (RB, ARI) | `8122` | Zonovan Knight (RB, ARI) | nickname "Bam" vs legal "Zonovan" |
| `2020` | Matthew Hibner (TE, BAL) | `13324` | Matt Hibner (TE, BAL) | Matthew vs Matt (2026 rookie — IS in the Sleeper dump) |

### 2b. Duplicate-name cases resolved by tiebreaker (verify-once, then safe)

| KTC playerID | Name (pos) | Sleeper candidates | Resolution |
|---|---|---|---|
| `1812` | Kyle Williams (WR, NEP) | **3** WR "Kyle Williams" in Sleeper: `12547` (NE, active, age 23 — 2025 3rd-rounder), `7437` (inactive, age 23), `638` (inactive, age 30); plus a DT `94` excluded by position | → `12547` via team tiebreak (NEP→NE) |
| `1570` | Frank Gore Jr. (RB, BUF) | suffix-strip collides with retired Frank Gore `232` (RB, null, age 38); Jr. is `11573` (RB, BUF, age 24) — note Sleeper stores Jr.'s `full_name` as plain "Frank Gore" | → `11573` via team tiebreak |
| `365` | Josh Allen (QB, BUF) | Sleeper has two Josh Allens, but the second is a LB — **excluded automatically by the position filter** | → `4984` (unique after position filter) |

Same pattern protects Lamar Jackson (QB `4881` vs a DB namesake) and every other cross-position namesake: **the position filter, not the name, is what makes this join safe.** The two WR/RB same-position duplicates above are the only ones that reached the tiebreak stage.

### 2c. Team-field disagreements among matched players (do NOT use team as a join key)

19 of 464 matched records disagree on team even after code translation — all are offseason-move / signing-window artifacts, and every one was still matched correctly via name+position:

- **KTC says `FA`, Sleeper has `null` — agree in substance (9):** Stefon Diggs (2641), Deebo Samuel (2336), Tyreek Hill (2141), Najee Harris (1556), Keenan Allen (1502) — all five **rostered** in the league; Jonnu Smith (1156), Joe Mixon (946), Zach Ertz (841), Antonio Gibson (589) — league FAs.
- **KTC lists an NFL team but Sleeper says `null` (10; KTC is ahead of Sleeper on these signings):** Javon Baker (SFO, 1284), Gabriel Davis (BUF, 1282), David Bell (CLE, 1187), Le'Veon Moss (MIA, 1093), Hassan Haskins (LAC, 1056), Alexander Mattison (MIA, 972), Zay Jones (ARI, 650), Brandin Cooks (BUF, 649), Harrison Bryant (SEA, 631), Ray-Ray McCloud (NYG, 586).

### 2d. Saved crosswalk file schema

`/home/bgram/dev/dynasty-bot/data/ktc_sleeper_map.json`:

```
{
  "_meta": { built, source_ktc scrape meta, league_id, match_rate, normalization rule, ... },
  "team_code_map_ktc_to_sleeper": { "GBP": "GB", ..., "FA": null },
  "manual_overrides": { "<ktc playerID>": "<sleeper player_id>", ... 5 entries },
  "crosswalk": {
    "<ktc playerID>": {
      "sleeper_id", "ktc_name", "sleeper_name", "position",
      "ktc_team", "sleeper_team", "oneqb_value", "rookie", "match_method"
    }, ... 464 entries
  }
}
```

---

## 3. Per-roster KTC 1QB totals (first roster-strength-vs-league table)

Method: for each roster, sum `oneQBValues.value` over all matched players in `players[]`. `taxi[]` and `reserve[]` are **subsets of `players[]`** on every roster (verified), so *total = active + taxi*, and IR/reserve players count inside "active" here. 251 unique players are rostered league-wide; **250 of 251 have a KTC value** — the only unvalued rostered player is **Darren Waller (Sleeper `2505`, TE, team null — not in KTC's top 464), on roster 4**.

| Rk | roster_id | Team (owner) | **Total** | QB | RB | WR | TE | Active | Taxi | KTC-valued |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 10 | She Kraft on myJohnston (NoahMoell) | **92,589** | 13,866 | 23,898 | 45,786 | 9,039 | 89,272 | 3,317 | 20/20 |
| 2 | 7 | Breece Lightnin' (joeydavis299) | **91,448** | 14,257 | 29,236 | 34,692 | 13,263 | 83,698 | 7,750 | 22/22 |
| 3 | 11 | Jordon Belichick (DrewR87) | **90,890** | 10,955 | 31,930 | 41,414 | 6,591 | 86,723 | 4,167 | 22/22 |
| 4 | 4 | **what would it take (bengramling)** | **87,173** | 11,095 | 34,349 | 30,860 | 10,869 | 79,740 | 7,433 | 20/21 |
| 5 | 6 | Skattebo Memorial Tour (millj) | **85,957** | 11,230 | 32,202 | 33,803 | 8,722 | 76,067 | 9,890 | 22/22 |
| 6 | 1 | School of Brock (cmgaither43) | **84,869** | 15,824 | 24,764 | 28,899 | 15,382 | 80,397 | 4,472 | 21/21 |
| 7 | 5 | Bed, Bath, and Bijan (trdouglas) | **84,415** | 16,243 | 23,872 | 30,801 | 13,499 | 79,673 | 4,742 | 22/22 |
| 8 | 2 | Naber-hood Watch (jaketoppen) | **80,363** | 11,452 | 31,136 | 20,693 | 17,082 | 80,363 | 0 | 20/20 |
| 9 | 3 | Bleacher Creatures (Jukinski) | **79,934** | 10,767 | 18,625 | 38,962 | 11,580 | 75,903 | 4,031 | 23/23 |
| 10 | 12 | Tua Deez Nuts (ronakpatel32) | **76,640** | 7,410 | 15,742 | 43,867 | 9,621 | 76,640 | 0 | 18/18 |
| 11 | 8 | vishan (no team name) | **75,248** | 15,436 | 16,995 | 26,198 | 16,619 | 72,883 | 2,365 | 20/20 |
| 12 | 9 | The Tet Offensive (josbaski) | **69,929** | 9,822 | 17,303 | 39,541 | 3,263 | 62,683 | 7,246 | 20/20 |

- League total: **999,455**; mean **83,288**; median **84,642**; spread rank 1→12 is 22,660 (≈2.3× a Bijan Robinson, the current KTC #1 at 9,998).
- **The user's roster is roster_id 4** (owner_id `1095425159290331136`, display_name `bengramling` — matches the account email bgramling18@gmail.com; flagged as inference from display name, everything else in this doc is direct data). It ranks **4th overall**, is **#1 in RB value (34,349)**, mid-pack at QB/TE, and only 8th in WR (30,860).
- Rosters 2 and 12 carry **zero taxi value** (no taxi players); roster 6 carries the most taxi value (9,890).
- Reserve (IR) slots in use, counted inside "active": roster 2 — George Kittle (`4217`, PUP) and Daniel Jones (`5870`); roster 3 — Zach Charbonnet (`9753`, PUP).
- Taxi squads (all matched, values are 1QB): r1 Jordan James 2710 + KeAndre Lambert-Smith 1762; r3 Tez Johnson 2603 + Kalel Mullings 1428; r4 Cam Ward 4432 + Elijah Arroyo 3001; r5 DJ Giddens 2487 + Jalen Milroe 2255; r6 Jayden Higgins 4301 + Jack Bech 3017 + LeQuint Allen 2572; r7 Ollie Gordon 2845 + Isaiah Bond 2502 + Trevor Etienne 2403; r8 Shedeur Sanders 2365; r9 Elic Ayomanor 3070 + Dont'e Thornton 2390 + Jimmy Horn 1786; r10 Jaylin Noel 3317; r11 Phil Mafah 1503 + Efton Chism 1486 + Arian Smith 1178.
- This table measures **raw asset value only** — it excludes the 36 KTC `RDP` pick values and each team's actual owned 2026–future picks. Pick ownership must be layered in separately for true franchise value.

---

## 4. Free-agent pool (waiver-tab seed list)

Definition: every matched KTC player whose sleeper_id is **not** in the union of `players[]` (⊇ taxi ⊇ reserve) across all 12 rosters. Result: **214 of 464 KTC-valued players are unrostered** (250 rostered).

**Summary:** by position — WR 86, RB 57, TE 38, QB 33. Total pool value 363,082. Players ≥2000: 51; ≥1000: 161. **59 of the 214 are 2026 rookies.**

**Critical caveat for the waiver tab:** the league's 2026 rookie draft (draft_id `1327016687945392128`, 4 rounds linear, 48 picks) is still **pre_draft**. The entire top of this "FA" list is the undrafted 2026 rookie class — including four KTC **top-50 overall** assets: Jeremiyah Love (#10 overall, 7,762), Carnell Tate (#26, 6,428), Jordyn Tyson (#40, 6,011), Makai Lemon (#48, 5,652). These are rookie-draft inventory, not waiver adds; ~48 of the 59 rookies will be absorbed by the draft. The scoring system should split this pool into **rookie-draft-eligible** (`rookie: true`) vs **true waiver targets** (veterans — top of that sub-list: Greg Dulcich 2,662, Ja'Tavion Sanders 2,496, Jaylin Lane 2,432, Emanuel Wilson 2,410, Colby Parkinson 2,372, Darnell Washington 2,299, Calvin Ridley 2,278, Anthony Richardson 2,178).

Full pool, sorted by KTC 1QB value descending. Team column shows the Sleeper-form code where both sources agree; "X / FA" means KTC lists team X but Sleeper has the player as a free agent (`null`).

| # | KTC 1QB | Pos | Player | Sleeper ID | KTC ID | NFL team (KTC/Sleeper) | 2026 rookie |
|---|---|---|---|---|---|---|---|
| 1 | 7762 | RB | Jeremiyah Love | 13287 | 1934 | ARI | yes |
| 2 | 6428 | WR | Carnell Tate | 13279 | 1959 | TEN | yes |
| 3 | 6011 | WR | Jordyn Tyson | 13281 | 1960 | NO | yes |
| 4 | 5652 | WR | Makai Lemon | 13294 | 1961 | PHI | yes |
| 5 | 5504 | RB | Jadarian Price | 13286 | 1935 | SEA | yes |
| 6 | 5133 | WR | KC Concepcion | 13298 | 1963 | CLE | yes |
| 7 | 4767 | TE | Kenyon Sadiq | 13330 | 2005 | NYJ | yes |
| 8 | 4703 | QB | Fernando Mendoza | 13269 | 1924 | LV | yes |
| 9 | 4464 | WR | Omar Cooper Jr. | 13276 | 1964 | NYJ | yes |
| 10 | 4363 | WR | Denzel Boston | 13346 | 1962 | CLE | yes |
| 11 | 4236 | TE | Eli Stowers | 13349 | 2006 | PHI | yes |
| 12 | 3874 | RB | Jonah Coleman | 13345 | 1939 | DEN | yes |
| 13 | 3736 | WR | Chris Bell | 13311 | 1968 | MIA | yes |
| 14 | 3644 | WR | Antonio Williams | 13301 | 1974 | WAS | yes |
| 15 | 3552 | WR | Germie Bernard | 13274 | 1965 | PIT | yes |
| 16 | 3536 | RB | Nicholas Singleton | 13288 | 1938 | TEN | yes |
| 17 | 3336 | WR | Zachariah Branch | 13320 | 1969 | ATL | yes |
| 18 | 3290 | WR | De'Zhaun Stribling | 13417 | 1976 | SF | yes |
| 19 | 3277 | WR | Malachi Fields | 13285 | 1973 | NYG | yes |
| 20 | 3274 | WR | Elijah Sarratt | 13268 | 1967 | BAL | yes |
| 21 | 3236 | QB | Ty Simpson | 13275 | 1925 | LAR | yes |
| 22 | 3141 | RB | Kaytron Allen | 13405 | 1940 | WAS | yes |
| 23 | 3126 | WR | Ted Hurst | 13317 | 1982 | TB | yes |
| 24 | 3117 | RB | Emmett Johnson | 13337 | 1936 | KC | yes |
| 25 | 3072 | WR | Chris Brazzell II | 13353 | 1971 | CAR | yes |
| 26 | 3068 | WR | Skyler Bell | 13402 | 1970 | BUF | yes |
| 27 | 2927 | WR | Ja'Kobi Lane | 13293 | 1979 | BAL | yes |
| 28 | 2866 | RB | Mike Washington Jr. | 13305 | 1944 | LV | yes |
| 29 | 2796 | TE | Max Klare | 13278 | 2009 | LAR | yes |
| 30 | 2662 | TE | Greg Dulcich | 8172 | 1256 | MIA |  |
| 31 | 2496 | TE | Ja'Tavion Sanders | 11600 | 1614 | CAR |  |
| 32 | 2469 | RB | Demond Claiborne | 13347 | 1943 | MIN | yes |
| 33 | 2432 | WR | Jaylin Lane | 12641 | 1816 | WAS |  |
| 34 | 2410 | RB | Emanuel Wilson | 11435 | 1515 | SEA |  |
| 35 | 2388 | WR | Kevin Coleman | 13338 | 1990 | MIA | yes |
| 36 | 2372 | TE | Colby Parkinson | 6865 | 565 | LAR |  |
| 37 | 2299 | TE | Darnell Washington | 9479 | 1431 | PIT |  |
| 38 | 2282 | RB | Kaelon Black | 13414 | 1947 | SF | yes |
| 39 | 2282 | RB | Isaiah Davis | 11571 | 1635 | NYJ |  |
| 40 | 2278 | WR | Calvin Ridley | 4981 | 293 | TEN |  |
| 41 | 2275 | TE | Eli Raridon | 13421 | 2018 | NE | yes |
| 42 | 2207 | RB | Brashard Smith | 12455 | 1749 | KC |  |
| 43 | 2205 | RB | Tahj Brooks | 12543 | 1758 | CIN |  |
| 44 | 2202 | WR | Jalen Royals | 12505 | 1786 | KC |  |
| 45 | 2178 | QB | Anthony Richardson | 9229 | 1405 | IND |  |
| 46 | 2177 | TE | Oscar Delp | 13319 | 2013 | NO | yes |
| 47 | 2170 | WR | Caleb Douglas | 13296 | 2016 | MIA | yes |
| 48 | 2162 | WR | Tyquan Thornton | 8188 | 1246 | KC |  |
| 49 | 2136 | TE | Luke Musgrave | 9481 | 1430 | GB |  |
| 50 | 2133 | TE | Ben Sinnott | 11596 | 1615 | WAS |  |
| 51 | 2018 | TE | Dawson Knox | 5906 | 88 | BUF |  |
| 52 | 1967 | RB | Jarquez Hunter | 11569 | 1764 | LAR |  |
| 53 | 1962 | WR | Jahan Dotson | 8119 | 1272 | ATL |  |
| 54 | 1959 | TE | Justin Joly | 13400 | 2010 | DEN | yes |
| 55 | 1934 | WR | Treylon Burks | 8135 | 1269 | WAS |  |
| 56 | 1924 | WR | Roman Wilson | 11630 | 1600 | PIT |  |
| 57 | 1922 | WR | Bryce Lance | 13420 | 1981 | NO | yes |
| 58 | 1913 | WR | Xavier Hutchinson | 10218 | 1454 | HOU |  |
| 59 | 1897 | RB | Will Shipley | 11577 | 1572 | PHI |  |
| 60 | 1870 | WR | Brenen Thompson | 13380 | 1991 | LAC | yes |
| 61 | 1868 | WR | Joshua Palmer | 7670 | 1065 | BUF |  |
| 62 | 1860 | WR | Tutu Atwell | 7562 | 1078 | MIA |  |
| 63 | 1840 | WR | Darius Slayton | 6149 | 77 | NYG |  |
| 64 | 1818 | RB | Isaac Guerendo | 11651 | 1626 | SF |  |
| 65 | 1816 | RB | Eli Heidenreich | 13423 | 2036 | PIT | yes |
| 66 | 1807 | WR | Jordan Whittington | 11623 | 1604 | LAR |  |
| 67 | 1799 | RB | Chris Brooks | 11370 | 1490 | GB |  |
| 68 | 1784 | RB | Justice Hill | 5995 | 368 | BAL |  |
| 69 | 1776 | RB | Jerome Ford | 8143 | 1229 | WAS |  |
| 70 | 1774 | WR | Zavion Thomas | 13411 | 1983 | CHI | yes |
| 71 | 1772 | TE | Noah Gray | 7828 | 1059 | KC |  |
| 72 | 1772 | TE | Mike Gesicki | 4993 | 330 | CIN |  |
| 73 | 1764 | RB | Malik Davis | 8800 | 1197 | DAL |  |
| 74 | 1730 | WR | Calvin Austin III | 8125 | 1262 | NYG |  |
| 75 | 1722 | TE | Erick All | 11592 | 1616 | CIN |  |
| 76 | 1706 | WR | John Metchie | 8147 | 1276 | CAR |  |
| 77 | 1702 | TE | Noah Fant | 5857 | 243 | NO |  |
| 78 | 1692 | WR | Devontez Walker | 11629 | 1592 | BAL |  |
| 79 | 1691 | WR | Ja'Lynn Polk | 11619 | 1602 | NO |  |
| 80 | 1679 | TE | Daniel Bellinger | 8225 | 1322 | TEN |  |
| 81 | 1662 | RB | Roschon Johnson | 10235 | 1390 | CHI |  |
| 82 | 1658 | TE | Tommy Tremble | 7694 | 1054 | CAR |  |
| 83 | 1645 | RB | Damien Martinez | 12462 | 1754 | GB |  |
| 84 | 1620 | TE | Cade Stover | 11599 | 1613 | HOU |  |
| 85 | 1611 | RB | Adam Randall | 13302 | 2026 | BAL | yes |
| 86 | 1604 | WR | Dyami Brown | 7587 | 1069 | WAS |  |
| 87 | 1589 | QB | Will Howard | 12511 | 1736 | PIT |  |
| 88 | 1588 | RB | Jaleel McLaughlin | 11439 | 1486 | DEN |  |
| 89 | 1562 | QB | Quinn Ewers | 12500 | 1734 | MIA |  |
| 90 | 1550 | TE | Tyler Higbee | 3271 | 159 | LAR |  |
| 91 | 1540 | WR | Tahj Washington | 11821 | 1644 | MIA |  |
| 92 | 1539 | WR | Kendrick Bourne | 4454 | 153 | ARI |  |
| 93 | 1531 | QB | Garrett Nussmeier | 13404 | 1927 | KC | yes |
| 94 | 1527 | RB | Ty Johnson | 6039 | 6 | BUF |  |
| 95 | 1517 | WR | Olamide Zaccheaus | 6271 | 609 | ATL |  |
| 96 | 1495 | RB | Rasheen Ali | 11570 | 1631 | BAL |  |
| 97 | 1495 | RB | Raheim Sanders | 12472 | 1762 | CLE |  |
| 98 | 1492 | WR | Tai Felton | 12496 | 1797 | MIN |  |
| 99 | 1482 | QB | Aaron Rodgers | 96 | 235 | PIT |  |
| 100 | 1471 | RB | Emari Demercado | 11199 | 1481 | KC |  |
| 101 | 1466 | TE | Michael Trigg | 13401 | 2008 | DAL | yes |
| 102 | 1461 | WR | Malachi Corley | 11617 | 1607 | CLE |  |
| 103 | 1460 | RB | Seth McGowan | 13424 | 1937 | IND | yes |
| 104 | 1460 | WR | Xavier Restrepo | 12520 | 1777 | TEN |  |
| 105 | 1428 | WR | Kameron Johnson | 11994 | 1701 | TB |  |
| 106 | 1425 | WR | Jordan Watkins | 12634 | 1817 | SF |  |
| 107 | 1421 | WR | Trey Palmer | 9492 | 1452 | NO |  |
| 108 | 1420 | WR | KaVontae Turpin | 8917 | 1336 | DAL |  |
| 109 | 1409 | QB | Joe Milton | 11557 | 1556 | DAL |  |
| 110 | 1399 | TE | Elijah Higgins | 10231 | 1469 | ARI |  |
| 111 | 1397 | WR | Elijah Moore | 7596 | 1012 | PHI |  |
| 112 | 1396 | TE | Luke Schoonmaker | 10871 | 1382 | DAL |  |
| 113 | 1363 | WR | Greg Dortch | 5970 | 10 | DET |  |
| 114 | 1362 | WR | Jacob Cowing | 11616 | 1611 | SF |  |
| 115 | 1353 | TE | Mitchell Evans | 12473 | 1809 | CAR |  |
| 116 | 1349 | WR | Jonathan Mingo | 10225 | 1450 | DAL |  |
| 117 | 1322 | QB | Dillon Gabriel | 12486 | 1737 | CLE |  |
| 118 | 1314 | RB | Bam Knight | 8122 | 1186 | ARI |  |
| 119 | 1304 | RB | Donovan Edwards | 12515 | 1757 | MIA |  |
| 120 | 1288 | QB | Spencer Rattler | 11562 | 1557 | NO |  |
| 121 | 1288 | WR | Deion Burks | 13333 | 1972 | IND | yes |
| 122 | 1286 | WR | CJ Daniels | 13270 | 1966 | LAR | yes |
| 123 | 1286 | RB | Dameon Pierce | 8129 | 1207 | PHI |  |
| 124 | 1284 | WR | Javon Baker | 11645 | 1608 | SFO / FA |  |
| 125 | 1283 | RB | Tyler Goodson | 8207 | 1189 | ATL |  |
| 126 | 1282 | WR | Gabriel Davis | 6943 | 533 | BUF / FA |  |
| 127 | 1269 | WR | Tyrell Shavers | 11377 | 1524 | BUF |  |
| 128 | 1250 | WR | Jake Bobo | 10867 | 1488 | SEA |  |
| 129 | 1247 | QB | Kirk Cousins | 1166 | 396 | LV |  |
| 130 | 1247 | WR | Mack Hollins | 4177 | 767 | NE |  |
| 131 | 1237 | QB | Cade Klubnik | 13303 | 1929 | NYJ | yes |
| 132 | 1224 | TE | Charlie Kolar | 8127 | 1254 | LAC |  |
| 133 | 1220 | WR | Bo Melton | 8204 | 1244 | GB |  |
| 134 | 1219 | RB | Tyler Badie | 8208 | 1206 | DEN |  |
| 135 | 1206 | RB | Israel Abanikanda | 9227 | 1383 | DAL |  |
| 136 | 1204 | RB | Kenny McIntosh | 10216 | 1385 | SEA |  |
| 137 | 1203 | TE | Brevin Jordan | 7568 | 1052 | HOU |  |
| 138 | 1187 | WR | Cyrus Allen | 13413 | 1980 | KC | yes |
| 139 | 1187 | WR | David Bell | 8118 | 1275 | CLE / FA |  |
| 140 | 1187 | TE | Davis Allen | 10214 | 1434 | LAR |  |
| 141 | 1163 | WR | Isaiah Hodgins | 6920 | 561 | NYG |  |
| 142 | 1161 | RB | Michael Carter | 7607 | 1035 | TEN |  |
| 143 | 1156 | TE | Jonnu Smith | 4144 | 84 | FA |  |
| 144 | 1152 | WR | Nick Westbrook-Ikhine | 7496 | 950 | IND |  |
| 145 | 1143 | WR | Tyler Scott | 9490 | 1436 | LAR |  |
| 146 | 1130 | TE | Jared Wiley | 11595 | 1619 | KC |  |
| 147 | 1120 | RB | J'Mari Taylor | 13348 | 1949 | JAX | yes |
| 148 | 1111 | RB | Frank Gore Jr. | 11573 | 1570 | BUF |  |
| 149 | 1106 | RB | Kendall Milton | 11649 | 1577 | CIN |  |
| 150 | 1104 | WR | Mason Tipton | 11895 | 1686 | NO |  |
| 151 | 1093 | RB | Le'Veon Moss | 13300 | 1941 | MIA / FA | yes |
| 152 | 1084 | WR | Xavier Gipson | 11306 | 1504 | NYG |  |
| 153 | 1082 | WR | Skyy Moore | 8168 | 1283 | GB |  |
| 154 | 1066 | RB | Sione Vaki | 11729 | 1627 | DET |  |
| 155 | 1056 | RB | Hassan Haskins | 8123 | 1191 | LAC / FA |  |
| 156 | 1045 | QB | Jameis Winston | 2306 | 413 | NYG |  |
| 157 | 1032 | TE | Sam Roush | 13322 | 2011 | CHI | yes |
| 158 | 1032 | WR | Brenden Rice | 11621 | 1594 | GB |  |
| 159 | 1028 | WR | Barion Brown | 13533 | 2003 | NO | yes |
| 160 | 1019 | WR | Lil'Jordan Humphrey | 5938 | 177 | DEN |  |
| 161 | 1004 | TE | Brock Wright | 7891 | 1162 | DET |  |
| 162 | 999 | WR | Demarcus Robinson | 3286 | 52 | SF |  |
| 163 | 992 | RB | Jawhar Jordan | 11588 | 1641 | HOU |  |
| 164 | 986 | WR | Jamari Thrash | 11633 | 1595 | CLE |  |
| 165 | 977 | RB | Jam Miller | 13403 | 1948 | NE | yes |
| 166 | 972 | RB | Alexander Mattison | 5987 | 326 | MIA / FA |  |
| 167 | 972 | WR | Bub Means | 11748 | 1634 | NO |  |
| 168 | 946 | RB | Joe Mixon | 4018 | 273 | FA |  |
| 169 | 943 | RB | Samaje Perine | 4147 | 785 | CIN |  |
| 170 | 910 | TE | Matthew Hibner | 13324 | 2020 | BAL | yes |
| 171 | 892 | QB | Marcus Mariota | 2307 | 23 | WAS |  |
| 172 | 886 | QB | Deshaun Watson | 4017 | 261 | CLE |  |
| 173 | 879 | RB | Ty Chandler | 8230 | 1182 | NO |  |
| 174 | 863 | RB | Zavier Scott | 11299 | 1898 | MIN |  |
| 175 | 850 | WR | Johnny Wilson | 11636 | 1596 | PHI |  |
| 176 | 841 | TE | Zach Ertz | 1339 | 305 | FA |  |
| 177 | 811 | WR | Ainias Smith | 11615 | 1624 | CAR |  |
| 178 | 806 | WR | Derius Davis | 10234 | 1473 | LAC |  |
| 179 | 798 | TE | Jack Endries | 13282 | 2007 | CIN | yes |
| 180 | 789 | RB | Elijah Mitchell | 7561 | 1013 | PHI |  |
| 181 | 787 | WR | Tyler Johnson | 6960 | 572 | DAL |  |
| 182 | 778 | WR | Van Jefferson | 6853 | 578 | WAS |  |
| 183 | 776 | RB | AJ Dillon | 6828 | 631 | CAR |  |
| 184 | 741 | RB | Terrell Jennings | 12412 | 1720 | NE |  |
| 185 | 726 | RB | Jeremy McNichols | 4219 | 782 | WAS |  |
| 186 | 692 | WR | Malik Heath | 11210 | 1502 | ATL |  |
| 187 | 688 | TE | Jeremy Ruckert | 8145 | 1255 | NYJ |  |
| 188 | 680 | WR | LaJohntay Wester | 12699 | 1823 | BAL |  |
| 189 | 674 | RB | Dylan Laube | 11574 | 1584 | LV |  |
| 190 | 650 | WR | Zay Jones | 4080 | 327 | ARI / FA |  |
| 191 | 649 | WR | Brandin Cooks | 2197 | 307 | BUF / FA |  |
| 192 | 643 | QB | Trey Lance | 7610 | 1017 | LAC |  |
| 193 | 641 | QB | Tyler Huntley | 7083 | 618 | BAL |  |
| 194 | 631 | TE | Harrison Bryant | 6850 | 752 | SEA / FA |  |
| 195 | 619 | TE | Josh Oliver | 5973 | 7 | MIN |  |
| 196 | 604 | QB | Sam Howell | 8162 | 1209 | DAL |  |
| 197 | 596 | QB | Zach Wilson | 7538 | 1016 | NO |  |
| 198 | 589 | QB | Kenny Pickett | 8160 | 1208 | CAR |  |
| 199 | 589 | RB | Antonio Gibson | 6945 | 584 | FA |  |
| 200 | 588 | QB | Carson Wentz | 3161 | 258 | MIN |  |
| 201 | 588 | WR | Kalif Raymond | 3634 | 822 | CHI |  |
| 202 | 586 | WR | Ray-Ray McCloud | 5096 | 646 | NYG / FA |  |
| 203 | 548 | QB | Aidan O'Connell | 10866 | 1412 | LV |  |
| 204 | 528 | QB | Will Levis | 9999 | 1402 | TEN |  |
| 205 | 468 | QB | Tanner McKee | 9230 | 1218 | PHI |  |
| 206 | 415 | QB | Mason Rudolph | 4972 | 110 | PIT |  |
| 207 | 413 | QB | Drew Lock | 5854 | 33 | SEA |  |
| 208 | 389 | QB | Gardner Minshew | 6011 | 47 | ARI |  |
| 209 | 275 | QB | Davis Mills | 7585 | 1029 | HOU |  |
| 210 | 258 | QB | Kyle McCord | 12494 | 1738 | GB |  |
| 211 | 186 | QB | Drew Allar | 13289 | 1930 | PIT | yes |
| 212 | 168 | QB | Cole Payton | 13335 | 2027 | PHI | yes |
| 213 | 167 | QB | Taylen Green | 13306 | 2029 | CLE | yes |
| 214 | 214 (val 138) | QB | Carson Beck | 13272 | 1928 | ARI | yes |

*(Row 214 value is 138 — the lowest-valued KTC asset in the pool.)*

**KTC-coverage depth note:** of KTC's top 50 overall, 46 are rostered (the 4 exceptions are the undrafted rookies above); top 100 → 90 rostered; top 150 → 134; top 200 → 172. The league has fully absorbed the veteran top of the KTC board — real waiver value starts around KTC ~2600 and below.

---

## 5. Facts the scoring system must respect

1. **Join only through `ktc_sleeper_map.json`** — never re-join by team (19/464 team disagreements) and never by raw name (nickname variants, suffix collisions, cross-position namesakes like Josh Allen QB/LB).
2. **KTC has no Sleeper ID natively** (only `mflid`); this crosswalk is the load-bearing bridge. When re-scraping KTC, re-run the join and treat any KTC `playerID` absent from `crosswalk` ∪ `manual_overrides` as a new-player alert requiring the same normalize→position→tiebreak procedure.
3. KTC `playerID` values are stable integers (e.g., Josh Allen = 365 across scrapes); Sleeper `player_id` values are stable strings. Both are safe keys.
4. Only assets with `position != 'RDP'` map to players; the 36 RDP records are generic pick values (2026–2028 rounds) usable later for pick valuation.
5. Rostered non-KTC players exist (currently exactly one: Darren Waller `2505`) — sum functions must default missing KTC value to 0, not error.
6. `taxi` and `reserve` are subsets of `players` in the Sleeper roster payload — never add them to `players` totals or value will be double-counted.
7. FA pool must be filtered by `rookie` flag while the 2026 rookie draft (pre_draft) is pending, or the waiver tab will recommend "adding" the 1.01.
