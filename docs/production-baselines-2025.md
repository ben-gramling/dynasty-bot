# Chicago Dynasty — 2025 Weekly Matchup Data (players_points): Season Totals, Replacement Baselines, Roster Production, Manager Efficiency

Gap-filling addendum. All figures below are computed from the actual Sleeper per-player weekly scores for the completed 2025 season of "Chicago Dynasty" (league_id `1251359014202114048`, 12-team 1QB dynasty, full PPR, 4-pt pass TD). This is the ground-truth dataset for replacement-level baselines and league-strength history.

## 1. Data provenance and files

Fetched `https://api.sleeper.app/v1/league/1251359014202114048/matchups/{week}` for every week 1–17 (the league's full scored season: `settings.leg = 17`, `last_scored_leg = 17`). Saved to:

- `/tmp/claude-1000/-home-bgram-dev-dynasty-bot/9d23798c-22b9-434a-b902-71d156ef37bd/scratchpad/matchups25_w{1..17}.json` — 12 rows per week, every week.
- Derived per-player season table saved to `/tmp/claude-1000/-home-bgram-dev-dynasty-bot/9d23798c-22b9-434a-b902-71d156ef37bd/scratchpad/player_season_2025.json` (335 rows: pid, name, pos, team, total, weeks_rostered, weeks_nonzero, weeks_started, ppw_rostered, ppw_active).

**Row schema (confirmed on live data):** `roster_id`, `matchup_id` (int, or `null` — see §2), `points` (team actual score), `custom_points` (always `null` here), `starters` (9 player_ids in slot order QB, RB, RB, WR, WR, WR, TE, FLEX, FLEX), `starters_points` (9 floats, slot-aligned), `players` (all rostered player_ids that week, 19–24 per team), `players_points` (map player_id → points for every rostered player, bench included).

Names/positions joined from `players_nfl.json` in the same scratchpad. **Caveat:** the `team` field in players_nfl.json is the player's *current* (July 2026) NFL team, not their 2025 team (e.g., A.J. Brown shows NE, George Pickens DAL, Travis Etienne NO). Positions are reliable.

## 2. Critical verification: playoff weeks 15–17 are fully populated for ALL 12 rosters

**Verified: YES — `players_points`, `starters`, and `starters_points` are populated for all 12 rosters in weeks 15, 16, and 17, including teams not in any bracket game that week.** Non-participants are identifiable only by `matchup_id: null`; their scores are real (e.g., wk 17 roster 5 scored 143.34 with `matchup_id: null`). Rosters with `matchup_id: null`: week 15 → {4, 7, 8, 11} (7 and 11 were the playoff byes; 4 and 8 consolation byes); week 16 → none (all 12 played); week 17 → {3, 5, 10, 12} (eliminated after week 16).

**Consequence for the scoring system:** season totals and weekly baselines can and should be computed over all 17 weeks uniformly; no imputation is needed for playoff weeks. One data quirk found: exactly one empty starter slot all season — week 17, roster 9, TE slot contained `"0"` (0.00 pts). No duplicate player-week entries exist (each player appears on exactly one roster per week; verified 0 collisions across 204 team-weeks).

**Semantics caveat for totals:** `players_points` covers only weeks a player was *rostered in this league*. A midseason pickup's earlier weeks are absent (e.g., Jaxson Dart appears 13 active weeks). Season totals are therefore "points while rostered in this league." Per-active-week averages (`ppw_active` = total ÷ weeks with nonzero points) largely correct for this and for byes/injuries, and are the recommended per-game rate metric.

## 3. Scoring and season-structure context (from league25.json, verified)

- Full PPR (`rec: 1.0`), `pass_td: 4`, `pass_yd: 0.04`, `rush_yd/rec_yd: 0.1`, `pass_int: -1`, `fum_lost: -2`, `rush_td/rec_td: 6`, all 2-pt conversions: 2. K/DEF scoring exists in settings but no K/DEF slots — lineup is QB/RB/RB/WR/WR/WR/TE/FLEX/FLEX + 10 BN.
- Regular season = weeks 1–14 (14 games), playoffs weeks 15–17, 6 playoff teams, top-2 seeds bye. Verified: every roster's `settings.fpts` in rosters25.json equals its sum of weekly `points` for weeks 1–14 exactly.
- 2025 bracket results (winners/losers bracket files, confirmed against weekly matchup_ids): **Champion: roster 2 (jaketoppen)**, beat roster 6 in the final; 3rd: roster 7 (joeydavis299, best record 11-3); 5th: roster 10. Losers-bracket final won by roster 8; roster 4 (the user) won the 7th-place game vs roster 1.
- League-wide average team score: **117.3 pts/team-week** (both weeks 1–14 and 1–17; total 23,933.6 pts over 204 team-weeks).

## 4. (a) Per-player 2025 season totals (this league's actual scoring)

335 distinct players were rostered at some point (46 QB, 98 RB, 144 WR, 47 TE). Columns: season total, active weeks (nonzero), points per active week, weeks in a starting lineup. Full table for all 335 players is in `player_season_2025.json`.

### QB (top 24 of 46 rostered)
| # | Player | Total | ActWks | PPW(act) | Started |
|---|--------|-------|--------|----------|---------|
| 1 | Josh Allen | 374.6 | 16 | 23.41 | 16 |
| 2 | Drake Maye | 344.2 | 16 | 21.51 | 13 |
| 3 | Matthew Stafford | 331.7 | 16 | 20.73 | 7 |
| 4 | Trevor Lawrence | 326.9 | 16 | 20.43 | 5 |
| 5 | Dak Prescott | 323.1 | 16 | 20.19 | 4 |
| 6 | Caleb Williams | 307.6 | 16 | 19.23 | 12 |
| 7 | Bo Nix | 305.3 | 16 | 19.08 | 15 |
| 8 | Jalen Hurts | 305.1 | 16 | 19.07 | 16 |
| 9 | Justin Herbert | 299.9 | 16 | 18.74 | 15 |
| 10 | Patrick Mahomes | 296.7 | 14 | 21.19 | 13 |
| 11 | Jared Goff | 288.8 | 16 | 18.05 | 6 |
| 12 | Baker Mayfield | 268.7 | 16 | 16.79 | 10 |
| 13 | Jordan Love | 241.1 | 15 | 16.08 | 2 |
| 14 | Sam Darnold | 240.6 | 16 | 15.04 | 1 |
| 15 | Jaxson Dart | 226.2 | 13 | 17.40 | 1 |
| 16 | Bryce Young | 211.5 | 15 | 14.10 | 0 |
| 17 | Daniel Jones | 205.0 | 12 | 17.08 | 4 |
| 18 | Lamar Jackson | 200.4 | 12 | 16.70 | 13 |
| 19 | C.J. Stroud | 199.3 | 13 | 15.33 | 6 |
| 20 | Cam Ward | 184.5 | 16 | 11.53 | 0 |
| 21 | Brock Purdy | 181.2 | 8 | 22.65 | 2 |
| 22 | Tua Tagovailoa | 175.7 | 14 | 12.55 | 2 |
| 23 | Aaron Rodgers | 167.8 | 12 | 13.98 | 0 |
| 24 | Jacoby Brissett | 152.3 | 8 | 19.04 | 6 |

### RB (top 36 of 98 rostered)
| # | Player | Total | ActWks | PPW(act) | Started |
|---|--------|-------|--------|----------|---------|
| 1 | Christian McCaffrey | 404.9 | 16 | 25.31 | 16 |
| 2 | Bijan Robinson | 363.5 | 16 | 22.72 | 16 |
| 3 | Jonathan Taylor | 356.4 | 16 | 22.27 | 16 |
| 4 | Jahmyr Gibbs | 346.6 | 16 | 21.66 | 16 |
| 5 | De'Von Achane | 322.8 | 16 | 20.18 | 16 |
| 6 | James Cook | 300.7 | 16 | 18.79 | 16 |
| 7 | Derrick Henry | 266.9 | 16 | 16.68 | 16 |
| 8 | Chase Brown | 263.6 | 16 | 16.48 | 16 |
| 9 | Kyren Williams | 252.2 | 16 | 15.76 | 16 |
| 10 | Travis Etienne | 249.1 | 16 | 15.57 | 15 |
| 11 | Javonte Williams | 242.8 | 16 | 15.17 | 14 |
| 12 | Josh Jacobs | 237.1 | 15 | 15.81 | 15 |
| 13 | Ashton Jeanty | 232.7 | 16 | 14.54 | 15 |
| 14 | Saquon Barkley | 232.3 | 16 | 14.52 | 16 |
| 15 | D'Andre Swift | 222.8 | 15 | 14.85 | 14 |
| 16 | Rico Dowdle | 213.3 | 16 | 13.33 | 10 |
| 17 | Breece Hall | 207.7 | 16 | 12.98 | 16 |
| 18 | RJ Harvey | 202.3 | 16 | 12.64 | 15 |
| 19 | Jaylen Warren | 202.2 | 15 | 13.48 | 16 |
| 20 | Kenny Gainwell | 200.9 | 16 | 12.56 | 5 |
| 21 | TreVeyon Henderson | 188.9 | 16 | 11.81 | 14 |
| 22 | Tony Pollard | 176.3 | 16 | 11.02 | 11 |
| 23 | Kenneth Walker | 174.6 | 16 | 10.91 | 14 |
| 24 | Quinshon Judkins | 169.8 | 14 | 12.13 | 13 |
| 25 | Zach Charbonnet | 162.7 | 15 | 10.85 | 15 |
| 26 | David Montgomery | 160.4 | 16 | 10.03 | 12 |
| 27 | Woody Marks | 144.3 | 15 | 9.62 | 12 |
| 28 | Rhamondre Stevenson | 143.5 | 13 | 11.04 | 5 |
| 29 | Kyle Monangai | 140.8 | 16 | 8.80 | 9 |
| 30 | Kareem Hunt | 138.9 | 16 | 8.68 | 12 |
| 31 | Jacory Croskey-Merritt | 137.4 | 16 | 8.59 | 11 |
| 32 | Rachaad White | 136.9 | 16 | 8.56 | 11 |
| 33 | Omarion Hampton | 135.7 | 9 | 15.08 | 5 |
| 34 | Tyrone Tracy | 132.9 | 14 | 9.49 | 10 |
| 35 | Cam Skattebo | 127.7 | 8 | 15.96 | 3 |
| 36 | Bucky Irving | 127.7 | 9 | 14.19 | 9 |

### WR (top 48 of 144 rostered)
| # | Player | Total | ActWks | PPW(act) | Started |
|---|--------|-------|--------|----------|---------|
| 1 | Puka Nacua | 349.0 | 15 | 23.27 | 15 |
| 2 | Jaxon Smith-Njigba | 345.5 | 16 | 21.59 | 16 |
| 3 | Amon-Ra St. Brown | 299.1 | 15 | 19.94 | 16 |
| 4 | Ja'Marr Chase | 290.0 | 15 | 19.33 | 15 |
| 5 | George Pickens | 290.0 | 16 | 18.12 | 16 |
| 6 | Chris Olave | 269.0 | 16 | 16.81 | 16 |
| 7 | Nico Collins | 226.2 | 15 | 15.08 | 15 |
| 8 | Davante Adams | 222.9 | 14 | 15.92 | 14 |
| 9 | A.J. Brown | 220.3 | 15 | 14.69 | 15 |
| 10 | Courtland Sutton | 218.2 | 16 | 13.64 | 14 |
| 11 | Wan'Dale Robinson | 217.9 | 16 | 13.62 | 9 |
| 12 | Zay Flowers | 213.5 | 16 | 13.34 | 16 |
| 13 | Jameson Williams | 206.5 | 14 | 14.75 | 16 |
| 14 | Stefon Diggs | 203.0 | 16 | 12.69 | 12 |
| 15 | Tetairoa McMillan | 200.9 | 16 | 12.56 | 16 |
| 16 | CeeDee Lamb | 199.5 | 12 | 16.62 | 13 |
| 17 | Michael Pittman | 199.3 | 16 | 12.46 | 16 |
| 18 | Jaylen Waddle | 194.1 | 16 | 12.13 | 14 |
| 19 | Emeka Egbuka | 193.9 | 16 | 12.12 | 16 |
| 20 | DeVonta Smith | 193.6 | 16 | 12.10 | 16 |
| 21 | Tee Higgins | 192.9 | 14 | 13.78 | 14 |
| 22 | DK Metcalf | 187.2 | 15 | 12.48 | 16 |
| 23 | Drake London | 184.1 | 11 | 16.74 | 11 |
| 24 | Deebo Samuel | 184.1 | 15 | 12.27 | 12 |
| 25 | Justin Jefferson | 183.1 | 16 | 11.44 | 16 |
| 26 | Ladd McConkey | 180.9 | 16 | 11.31 | 16 |
| 27 | Troy Franklin | 177.1 | 16 | 11.07 | 0 |
| 28 | Michael Wilson | 175.2 | 13 | 13.48 | 4 |
| 29 | Keenan Allen | 172.1 | 16 | 10.76 | 16 |
| 30 | Quentin Johnston | 171.2 | 12 | 14.27 | 10 |
| 31 | DJ Moore | 168.1 | 15 | 11.21 | 13 |
| 32 | Khalil Shakir | 166.4 | 16 | 10.40 | 15 |
| 33 | Jakobi Meyers | 166.4 | 15 | 11.09 | 12 |
| 34 | Jauan Jennings | 165.8 | 14 | 11.84 | 11 |
| 35 | Romeo Doubs | 165.4 | 15 | 11.03 | 8 |
| 36 | Rashid Shaheed | 155.4 | 17 | 9.14 | 17 |
| 37 | Alec Pierce | 154.1 | 13 | 11.85 | 9 |
| 38 | Rashee Rice | 150.1 | 8 | 18.76 | 8 |
| 39 | Rome Odunze | 146.1 | 11 | 13.28 | 12 |
| 40 | Tre Tucker | 142.9 | 14 | 10.21 | 9 |
| 41 | Jordan Addison | 133.3 | 12 | 11.11 | 10 |
| 42 | Christian Watson | 132.4 | 10 | 13.24 | 9 |
| 43 | Brian Thomas | 130.9 | 13 | 10.07 | 13 |
| 44 | Marquise Brown | 128.3 | 14 | 9.16 | 3 |
| 45 | Marvin Harrison | 127.8 | 11 | 11.62 | 9 |
| 46 | Josh Downs | 126.8 | 15 | 8.45 | 7 |
| 47 | Luther Burden | 120.4 | 14 | 8.60 | 3 |
| 48 | Chimere Dike | 120.4 | 16 | 7.52 | 8 |

### TE (top 18 of 47 rostered)
| # | Player | Total | ActWks | PPW(act) | Started |
|---|--------|-------|--------|----------|---------|
| 1 | Trey McBride | 302.4 | 16 | 18.90 | 16 |
| 2 | Kyle Pitts | 199.0 | 16 | 12.44 | 16 |
| 3 | Travis Kelce | 189.0 | 16 | 11.81 | 16 |
| 4 | Jake Ferguson | 186.6 | 15 | 12.44 | 11 |
| 5 | Harold Fannin | 186.4 | 16 | 11.65 | 12 |
| 6 | Dallas Goedert | 185.1 | 15 | 12.34 | 9 |
| 7 | Tyler Warren | 180.9 | 16 | 11.31 | 16 |
| 8 | Brock Bowers | 176.2 | 12 | 14.68 | 13 |
| 9 | Hunter Henry | 168.2 | 16 | 10.51 | 14 |
| 10 | Dalton Schultz | 160.6 | 15 | 10.71 | 10 |
| 11 | Juwan Johnson | 157.2 | 15 | 10.48 | 10 |
| 12 | George Kittle | 153.6 | 9 | 17.07 | 10 |
| 13 | Colston Loveland | 140.0 | 14 | 10.00 | 5 |
| 14 | Theo Johnson | 127.8 | 14 | 9.13 | 6 |
| 15 | Mark Andrews | 127.6 | 16 | 7.98 | 14 |
| 16 | Oronde Gadsden | 127.1 | 14 | 9.08 | 8 |
| 17 | Zach Ertz | 126.4 | 12 | 10.53 | 7 |
| 18 | Dalton Kincaid | 118.3 | 10 | 11.83 | 11 |

Notable single facts affecting valuation: Josh Allen was the QB1 by 30 pts; Trey McBride outscored TE2 by 103.4 pts (biggest positional gap in the league — elite TE is a massive weekly edge here); the RB1–RB5 tier (CMC/Bijan/Taylor/Gibbs/Achane, all 20+ ppw) towers over RB24 (~12 ppw); high-ppw short-sample players (Rashee Rice 18.76 over 8 wks, Omarion Hampton 15.08 over 9, Bucky Irving 14.19 over 9, Brock Purdy 22.65 over 8) need sample-size handling in any projection built from this data.

## 5. (b) Positional replacement-level anchors (12-team, 1QB/2RB/3WR/1TE/2FLEX)

Two methods, both restricted to players with ≥6 active weeks, ranked within the league-rostered pool. **Recommended primary: per-active-week (per-game) averages** — the total/17-style method (second table) punishes partial-season rostering and injuries and understates true weekly replacement value.

**By per-active-week average (recommended anchors):**

| Anchor | Player at rank | Weekly avg (pts) |
|--------|----------------|------------------|
| QB10 | Jalen Hurts | 19.07 |
| **QB12** | **Justin Herbert** | **18.74** |
| QB14 | Jaxson Dart | 17.40 |
| RB20 | Rico Dowdle | 13.33 |
| **RB24** | **Quinshon Judkins** | **12.13** |
| RB28 | Rhamondre Stevenson | 11.04 |
| WR30 | Jaylen Waddle | 12.13 |
| **WR36** | **Terry McLaurin** | **11.61** |
| WR42 | Troy Franklin | 11.07 |
| TE10 | Travis Kelce | 11.81 |
| **TE12** | **Tyler Warren** | **11.31** |
| TE14 | Zach Ertz | 10.53 |

**Flex boundary (combined RB+WR+TE ranking by per-active-week avg):** rank 48 = 13.23 (Mike Evans), **rank 54 = 12.48 (DK Metcalf)**, rank 60 = 12.13, rank 72 = 11.61, rank 84 = 11.02, rank 96 = 10.07 (Brian Thomas). Structural note: with 12 teams starting 24 RB + 36 WR + 12 TE + 24 FLEX, the *last starting* flex-eligible player is combined rank ~96 (≈10.1 ppw); the requested ~54th combined (≈12.5 ppw) sits inside the dedicated-starter range and is better read as a "solid weekly flex" bar than as absolute replacement level. Both are reported so the scoring system can choose its baseline.

**Cross-check anchors by season-total rate (total ÷ weeks rostered, includes byes/zero weeks):** QB12 = 16.99 (Goff), RB24 = 9.99 (Judkins), WR36 = 9.73 (Doubs), TE12 = 9.04 (Kittle), flex rank 54 = 10.77, rank 96 = 7.55.

**Headline replacement structure for VOR:** QB12 ≈ 18.7, RB24 ≈ 12.1, WR36 ≈ 11.6, TE12 ≈ 11.3, last-flex ≈ 10.1 ppw. So in this league's actual scoring: startable QBs are worth ~6.5+ ppw over any flex position's baseline; RB/WR/TE replacement levels are nearly identical (11–12 ppw), meaning positional scarcity at RB/WR/TE shows up at the *elite* end (top-5 RB ~20–25 ppw, TE1 ~19 ppw vs TE2 ~12.4), not the baseline.

## 6. (c) Per-roster weekly actual points and season positional shares

Weekly actual points (weeks 1–17; W1–14 = regular season, W15–17 = playoff/consolation weeks; all rosters scored all 17 weeks):

| RID | Owner | W1 | W2 | W3 | W4 | W5 | W6 | W7 | W8 | W9 | W10 | W11 | W12 | W13 | W14 | W15 | W16 | W17 | Sum1–14 | Sum1–17 |
|----|-------|----|----|----|----|----|----|----|----|----|----|----|----|----|----|----|----|----|--------|--------|
| 1 | cmgaither43 | 154.52 | 121.92 | 97.96 | 133.38 | 117.56 | 128.88 | 75.56 | 149.42 | 124.36 | 122.82 | 105.00 | 119.58 | 93.74 | 88.72 | 88.50 | 148.32 | 113.18 | 1633.42 | 1983.42 |
| 2 | jaketoppen | 127.72 | 137.00 | 112.48 | 110.78 | 105.24 | 138.24 | 113.74 | 81.78 | 101.16 | 133.90 | 109.70 | 118.46 | 131.04 | 92.86 | 197.20 | 142.86 | 139.68 | 1614.10 | 2093.84 |
| 3 | Jukinski | 106.72 | 86.64 | 89.28 | 123.26 | 148.04 | 101.18 | 87.58 | 89.30 | 147.80 | 101.30 | 103.12 | 85.56 | 94.16 | 108.64 | 118.28 | 97.70 | 71.80 | 1472.58 | 1760.36 |
| 4 | **bengramling (user)** | 71.22 | 90.34 | 98.30 | 133.20 | 170.14 | 93.50 | 79.54 | 103.62 | 129.10 | 106.96 | 109.84 | 90.32 | 87.30 | 98.26 | 108.80 | 157.26 | 94.10 | 1461.64 | 1821.80 |
| 5 | trdouglas | 117.62 | 129.68 | 108.30 | 138.42 | 100.74 | 140.06 | 123.30 | 123.68 | 108.30 | 137.90 | 128.54 | 82.56 | 114.14 | 100.86 | 85.60 | 123.20 | 143.34 | 1654.10 | 2006.24 |
| 6 | jmill00 | 115.58 | 101.64 | 123.14 | 109.60 | 124.90 | 163.22 | 126.04 | 133.06 | 129.40 | 131.02 | 114.50 | 137.46 | 106.40 | 106.50 | 135.40 | 150.70 | 91.40 | 1722.46 | 2099.96 |
| 7 | joeydavis299 | 107.78 | 118.00 | 116.12 | 117.16 | 162.16 | 120.04 | 135.52 | 130.74 | 165.04 | 109.72 | 116.30 | 153.12 | 127.72 | 107.44 | 117.82 | 102.50 | 141.36 | 1786.86 | 2148.54 |
| 8 | vishan | 146.76 | 107.72 | 90.32 | 108.86 | 98.42 | 74.30 | 109.62 | 147.82 | 116.92 | 83.24 | 113.08 | 83.02 | 93.92 | 107.44 | 116.42 | 58.90 | 67.98 | 1481.44 | 1724.74 |
| 9 | josbaski | 101.74 | 119.74 | 143.12 | 129.24 | 105.12 | 82.06 | 164.26 | 121.58 | 96.12 | 73.60 | 122.20 | 120.66 | 121.34 | 85.48 | 107.58 | 124.38 | 69.48 | 1586.26 | 1887.70 |
| 10 | NoahMoell | 134.72 | 146.78 | 125.06 | 144.00 | 134.94 | 124.98 | 170.44 | 139.16 | 112.90 | 94.92 | 77.68 | 117.08 | 143.34 | 113.30 | 132.96 | 125.90 | 105.82 | 1779.30 | 2143.98 |
| 11 | DrewR87 | 100.98 | 158.44 | 127.64 | 147.42 | 165.52 | 149.96 | 105.06 | 118.38 | 129.56 | 151.80 | 120.64 | 134.96 | 110.38 | 153.74 | 147.30 | 125.70 | 126.94 | 1874.48 | 2274.42 |
| 12 | ronakpatel32 | 134.96 | 119.10 | 129.32 | 85.88 | 116.70 | 69.70 | 147.90 | 108.52 | 128.56 | 117.94 | 90.72 | 160.42 | 102.04 | 133.56 | 97.10 | 157.94 | 88.20 | 1645.32 | 1988.56 |

Season positional production from **starting lineups** (weeks 1–17; points attributed by player position regardless of slot, so FLEX points count toward the flexed player's position):

| RID | Owner | QB pts | RB pts | WR pts | TE pts | Total | QB% | RB% | WR% | TE% |
|----|-------|--------|--------|--------|--------|-------|-----|-----|-----|-----|
| 1 | cmgaither43 | 232.7 | 594.2 | 937.2 | 219.3 | 1983.4 | 11.7 | 30.0 | 47.3 | 11.1 |
| 2 | jaketoppen | 289.1 | 652.6 | 631.7 | 520.5 | 2093.8 | 13.8 | 31.2 | 30.2 | 24.9 |
| 3 | Jukinski | 303.8 | 488.8 | 555.1 | 412.7 | 1760.4 | 17.3 | 27.8 | 31.5 | 23.4 |
| 4 | **bengramling (user)** | 237.4 | 834.4 | 584.4 | 165.6 | 1821.8 | 13.0 | 45.8 | 32.1 | 9.1 |
| 5 | trdouglas | 314.0 | 854.7 | 598.3 | 239.2 | 2006.2 | 15.7 | 42.6 | 29.8 | 11.9 |
| 6 | jmill00 | 333.3 | 770.6 | 793.9 | 202.2 | 2100.0 | 15.9 | 36.7 | 37.8 | 9.6 |
| 7 | joeydavis299 | 316.7 | 534.3 | 927.3 | 370.3 | 2148.5 | 14.7 | 24.9 | 43.2 | 17.2 |
| 8 | vishan | 404.0 | 442.1 | 620.4 | 258.2 | 1724.7 | 23.4 | 25.6 | 36.0 | 15.0 |
| 9 | josbaski | 323.0 | 532.3 | 913.8 | 118.6 | 1887.7 | 17.1 | 28.2 | 48.4 | 6.3 |
| 10 | NoahMoell | 395.5 | 510.6 | 1039.4 | 198.5 | 2144.0 | 18.4 | 23.8 | 48.5 | 9.3 |
| 11 | DrewR87 | 355.5 | 722.8 | 1052.5 | 143.6 | 2274.4 | 15.6 | 31.8 | 46.3 | 6.3 |
| 12 | ronakpatel32 | 240.3 | 782.6 | 815.3 | 150.4 | 1988.6 | 12.1 | 39.4 | 41.0 | 7.6 |

League-wide starter production split: **QB 15.7% / RB 32.3% / WR 39.6% / TE 12.5%** (3,745.3 / 7,720.0 / 9,469.3 / 2,999.1 of 23,933.6 total). The user's team (roster 4) had the league's most RB-skewed production (45.8%) and third-lowest TE share (9.1%); it also ranked 12th (last) in regular-season fpts despite ranking 9th in ppts.

## 7. (d) Manager efficiency (fpts / ppts)

From rosters25.json settings (`fpts`+`fpts_decimal/100`, `ppts`+`ppts_decimal/100`). **Validation performed:** an optimal-lineup solver (best QB, 2 RB, 3 WR, 1 TE, then best 2 remaining RB/WR/TE from each week's full `players_points`) reproduces Sleeper's `ppts` **exactly** for all 12 rosters over weeks 1–14 — proving (i) Sleeper's `ppts` is regular-season-only (weeks 1–14), and (ii) the same solver can be reused in the app to compute potential points for any roster/week. Full-season (1–17) efficiency computed with the same solver:

| RID | Owner | Record | fpts (1–14) | ppts (1–14) | Eff 1–14 | Actual 1–17 | Optimal 1–17 | Eff 1–17 |
|----|-------|--------|-------------|-------------|----------|-------------|--------------|----------|
| 7 | joeydavis299 | 11-3 | 1786.86 | 1979.80 | 90.3% | 2148.54 | 2400.24 | 89.5% |
| 9 | josbaski | 6-8 | 1586.26 | 1751.80 | 90.6% | 1887.70 | 2088.44 | 90.4% |
| 12 | ronakpatel32 | 5-9 | 1645.32 | 1843.78 | 89.2% | 1988.56 | 2264.24 | 87.8% |
| 2 | jaketoppen (champ) | 9-5 | 1614.10 | 1826.30 | 88.4% | 2093.84 | 2353.94 | 89.0% |
| 8 | vishan | 5-9 | 1481.44 | 1691.92 | 87.6% | 1724.74 | 2022.60 | 85.3% |
| 5 | trdouglas | 7-7 | 1654.10 | 1914.20 | 86.4% | 2006.24 | 2333.10 | 86.0% |
| 11 | DrewR87 | 9-5 | 1874.48 | 2185.42 | 85.8% | 2274.42 | 2622.56 | 86.7% |
| 10 | NoahMoell | 8-6 | 1779.30 | 2081.80 | 85.5% | 2143.98 | 2540.62 | 84.4% |
| 6 | jmill00 | 8-6 | 1722.46 | 2016.20 | 85.4% | 2099.96 | 2506.80 | 83.8% |
| 4 | **bengramling (user)** | 4-10 | 1461.64 | 1838.64 | **79.5%** | 1821.80 | 2308.10 | **78.9%** |
| 1 | cmgaither43 | 6-8 | 1633.42 | 2043.04 | 80.0% | 1983.42 | 2456.94 | 80.7% |
| 3 | Jukinski | 6-8 | 1472.58 | 1872.10 | 78.7% | 1760.36 | 2277.38 | 77.3% |

Facts relevant to the scoring system: DrewR87 (roster 11) had the most raw talent (highest ppts and actual, both windows) but lost points to lineup decisions; the champion (roster 2) was only 8th in ppts but 4th in efficiency plus a 197.2 playoff explosion. The user left 377.0 potential points on the bench weeks 1–14 (486.3 over 1–17) — 11th of 12 in efficiency — driven partly by breakout benchings (e.g., roster-wide pattern of high scores from non-started players; league-wide example: Troy Franklin scored 177.1 pts across 16 active weeks with 0 starts). Efficiency spread in this league is wide (77–90%), so a start/sit or "bench points at stackable positions" signal is a real differentiator, worth roughly 25–30 pts/week between the best and worst managers.

## 8. Summary of decisions this enables

1. Use all 17 weeks for player season totals and baselines — playoff weeks are fully populated for all 12 rosters (verified, §2).
2. Use per-active-week averages (min ~6 active weeks) for replacement anchors: QB12 ≈ 18.7, RB24 ≈ 12.1, WR36 ≈ 11.6, TE12 ≈ 11.3, last-flex (combined rank ~96) ≈ 10.1; requested combined rank 54 ≈ 12.5.
3. Sleeper `fpts`/`ppts` are weeks 1–14 only; the exact-match optimal-lineup solver (§7) can extend potential-points to any window and should be the app's canonical implementation.
4. `players_points` totals are "while rostered in this league"; correct for partial rostering via active-week rates before feeding a VOR model.
5. Player `team` fields joined from players_nfl.json reflect 2026 rosters, not 2025 — do not use them for 2025 context.