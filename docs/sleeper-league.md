# Sleeper League Knowledge: Chicago Dynasty

> Knowledge base for the dynasty-bot roster-decision scoring system. All data pulled live from the public Sleeper API on **2026-07-26**. Player names/teams/ages come from the full Sleeper player dump saved at `/tmp/claude-1000/-home-bgram-dev-dynasty-bot/9d23798c-22b9-434a-b902-71d156ef37bd/scratchpad/players_nfl.json` (14.6 MB, downloaded once).

## 0. Identity correction (IMPORTANT)

The task brief contained `undefined` for every ID. The real IDs were recovered and verified against the API:

- The league **"Chicago Dynasty" belongs to Sleeper account `BenGramling`** (display_name `bengramling`), **user_id `1095425159290331136`**.
- A second Sleeper account matching the user's handle also exists — `bgram`, user_id `729166377545469952` — but it is **not** in Chicago Dynasty (it owns 4 other leagues: C/O 2k18, The Dirty Dozen, CB Primetime, Show Us Ur Td Dynasty). dynasty-bot should treat `1095425159290331136` as the canonical user for this league.

## 1. Core IDs

| Item | Value |
|---|---|
| 2026 league_id (current, `pre_draft`) | **1312124603224555520** |
| 2025 league_id (predecessor, `complete`) | **1251359014202114048** |
| MY user_id (BenGramling / bengramling) | **1095425159290331136** |
| MY roster_id (both seasons) | **4** |
| MY team name | "what would it take" |
| 2026 rookie draft draft_id | **1327016687945392128** |
| 2025 startup draft draft_id | **1251359015015809024** |
| NFL state (at pull time) | season **2026**, week 0, season_type **off** |

## 2. League format (2026 league 1312124603224555520)

- **Name:** Chicago Dynasty · **Status:** pre_draft · **12 teams** · sport nfl · season 2026 (season_type regular)
- **Type:** `settings.type = 2` → **dynasty** (full roster carryover). `metadata.auto_continue = on`.
- **best_ball = 0** → weekly lineup-setting league (not best ball). `league_average_match = 0` (no extra league-median game).
- **No divisions** (no division settings/metadata present).
- **leg = 1, start_week = 1** (2025 league ended with `leg/last_scored_leg = 17`).

### 2.1 Roster construction

`roster_positions`: `QB, RB, RB, WR, WR, WR, TE, FLEX, FLEX, BN×10`

- **9 starters + 10 bench = 19 active roster spots.**
- **1QB league** — exactly one QB slot, **no SUPER_FLEX** (FLEX is RB/WR/TE only). QB values should be discounted vs superflex market values (KTC has a dedicated 1QB valuation — use that).
- **No K, no DEF, no IDP slots** — only QB/RB/WR/TE ever score.
- **IR:** `reserve_slots = 2`; only `reserve_allow_out = 1` → **IR eligibility is strictly players with game status OUT** (not IR-designation alone; COV/DNR/Doubtful/NA/Suspended all disallowed: all those flags = 0).
- **Taxi squad:** `taxi_slots = 3`, `taxi_years = 1`, **`taxi_allow_vets = 1`** (veterans allowed on taxi despite the 1-year setting), `taxi_deadline = 4` (taxi locks after leg/week 4). Max roster incl. taxi+IR = 19 + 3 + 2 = 24.
- `max_keepers = 1` (vestigial in dynasty — everyone is kept), `draft_rounds = 4` (rookie drafts are 4 rounds), `capacity_override = 0`.
- `bench_lock = 1` (bench players lock at kickoff), `max_subs = 2` with `sub_lock_if_starter_active = 0`, `sub_start_time_eligibility = 0` (limited in-game substitutions feature enabled, 2 per week).

### 2.2 Scoring settings — every entry, decoded

**Positions that can actually score: QB/RB/WR/TE only.** Kicker/defense entries exist in the settings blob (Sleeper defaults) but are **dead settings** — no K/DEF/IDP roster slot exists.

Passing:
| Setting | Value | Meaning |
|---|---|---|
| `pass_yd` | 0.04 | 1 pt per 25 passing yards |
| `pass_td` | 4.0 | **4 pts per passing TD** (not 6) |
| `pass_int` | -1.0 | -1 per INT thrown |
| `pass_2pt` | 2.0 | 2-pt conversion pass |

Rushing / Receiving:
| Setting | Value | Meaning |
|---|---|---|
| `rush_yd` / `rec_yd` | 0.1 | 1 pt per 10 yards |
| `rush_td` / `rec_td` | 6.0 | 6 pts per TD |
| `rec` | **1.0** | **Full PPR** |
| `rush_2pt` / `rec_2pt` | 2.0 | 2-pt conversions |

Turnovers / misc (applies to offensive players):
| Setting | Value | Meaning |
|---|---|---|
| `fum` | 0.0 | No penalty for a fumble that isn't lost |
| `fum_lost` | -2.0 | -2 per fumble lost |
| `fum_rec_td` | 6.0 | 6 pts for a fumble-recovery TD |

**No TE premium** (no `bonus_rec_te`), **no yardage/first-down bonuses of any kind** (no 100-yd/300-yd/40-yd-TD bonuses, no `bonus_rec_rb/wr`, no first-down points).

Dead settings (no eligible roster slot): kicking `fgm_0_19/20_29/30_39 = 3`, `fgm_40_49 = 4`, `fgm_50_59 = 5`, `fgm_60p = 6`, `fgmiss = -1`, `xpm = 1`, `xpmiss = -1`; team defense/ST `def_td/def_st_td/st_td = 6`, `sack = 1`, `int = 2` (defensive INT), `ff/st_ff/def_st_ff = 1`, `fum_rec/def_st_fum_rec/st_fum_rec` = 2/1/1, `safe = 2`, `blk_kick = 2`, points-allowed tiers `pts_allow_0 = 10, 1_6 = 7, 7_13 = 4, 14_20 = 1, 21_27 = 0, 28_34 = -1, 35p = -4`. (`idp_def_td = 6` existed in 2025, removed for 2026 — also dead.)

**Scoring-system implication:** This is a vanilla **1QB, full-PPR, 4-pt-pass-TD** format with 2 flexes and 3 starting WR. WRs and RBs carry standard PPR value, TEs get no boost, and QB value is materially lower than superflex KTC values. Deep starting lineups (9 starters from 4 positions across 12 teams = 108 starters weekly) make the RB/WR middle class relevant.

### 2.3 Waivers (how player acquisition works)

| Setting | Value | Meaning |
|---|---|---|
| `waiver_type` | 2 | **FAAB blind-bid auction** |
| `waiver_budget` | **50** | **$50 is the OFFSEASON budget only** (per league owner). Around **Aug 12**, when the season starts, the league switches to a **$200 in-season FAAB budget** — same as 2025, so historical 2025 bid sizes are directly comparable (no scaling). Offseason strategy: waivers process daily with little competition, so most offseason claims should be bid at **$0–$1** |
| `waiver_clear_days` | 1 | Dropped/new players clear waivers after 1 day |
| `daily_waivers` | 1 | Waivers process daily (continual), not one weekly run |
| `waiver_day_of_week` | 2 | Wednesday anchor day (Sleeper day code 0=Mon) |
| `daily_waivers_hour` | 0 | Processing at hour 0 (midnight) |
| `daily_waivers_days` | 5461 (2025: 5460) | Sleeper day-bitmask for which days waivers run |
| `disable_adds` | 0 | Adds allowed |
| `offseason_adds` | **1** | Offseason adds ENABLED for 2026 (was 0 in 2025) — waivers are live right now |
| `faab_suggestions` | 1 | Sleeper shows FAAB suggestions in-app |

### 2.4 Trades

| Setting | Value | Meaning |
|---|---|---|
| `trade_deadline` | **11** | No trades after week 11 |
| `trade_review_days` | **0** | Trades process **instantly** — no review period |
| `veto_votes_needed` | 6 | 6 votes to veto, but `veto_auto_poll = 0` (no automatic poll) and `veto_show_votes = 0`; with 0 review days vetoes are effectively moot |
| `pick_trading` | 1 | **Future draft-pick trading enabled** (2026/2027/2028 visible) |
| `disable_trades` | 0 | Trades enabled |

### 2.5 Playoffs

- `playoff_teams = 6`, `playoff_week_start = 15` → **6-team playoff, weeks 15–17**, 3 rounds, **top-2 seeds get first-round byes**.
- `playoff_round_type = 0` → one week per round. `playoff_seed_type = 0` → standard bracket (no re-seeding). `playoff_type = 0` → standard playoff.
- 14-week regular season (weeks 1–14), no divisions → seeding by record, points as tiebreak.

## 3. Teams: owner ↔ roster mapping (identical roster_ids both seasons)

| roster_id | Sleeper user_id | display_name | Team name (2026) | 2026 draft slot |
|---|---|---|---|---|
| 1 | 964266240745226240 | cmgaither43 | School of Brock (2025: "F*ck Oronde Find Out") | 6 |
| 2 | 815026025661583360 | jaketoppen | Naber-hood Watch | 12 |
| 3 | 939924299933175808 | Jukinski | Bleacher Creatures | 4 |
| **4** | **1095425159290331136** | **bengramling** | **what would it take — MY TEAM** | **1** |
| 5 | 996848070979629056 | trdouglas | Bed, Bath, and Bijan | 7 |
| 6 | 964264771371487232 | millj (2025: jmill00) | Skattebo Memorial Tour | 11 |
| 7 | 964266016853307392 | joeydavis299 | Breece Lightnin' | 10 |
| 8 | 1050975911891357696 | vishan | (no team name) | 2 |
| 9 | 731001489828503552 | josbaski | The Tet Offensive | 5 |
| 10 | 1251373941738450944 | NoahMoell | She Kraft on myJohnston | 8 |
| 11 | 374691873518063616 | DrewR87 | Jordon Belichick | 9 |
| 12 | 1051305245869064192 | ronakpatel32 | Tua Deez Nuts | 3 |

No co-owners on any roster.

## 4. 2025 season results (league 1251359014202114048, complete)

Regular season 14 weeks; playoffs weeks 15–17. Champion per bracket + `latest_league_winner_roster_id = 2`.

### Final standings (playoff-adjusted)

| Finish | Team | Record | PF | PA | Note |
|---|---|---|---|---|---|
| 1 | jaketoppen (2) | 9-5 | 1614.10 | 1533.82 | **CHAMPION** (beat millj in final) |
| 2 | millj (6) | 8-6 | 1722.46 | 1605.18 | Runner-up |
| 3 | joeydavis299 (7) | 11-3 | 1786.86 | 1536.60 | Best record; lost semi to millj |
| 4 | DrewR87 (11) | 9-5 | 1874.48 | 1554.50 | **Highest PF in league**; lost semi to jaketoppen |
| 5 | NoahMoell (10) | 8-6 | 1779.30 | 1707.72 | |
| 6 | trdouglas (5) | 7-7 | 1654.10 | 1639.14 | |
| 7 | vishan (8) | 5-9 | 1481.44 | 1765.92 | Won consolation bracket |
| 8 | josbaski (9) | 6-8 | 1586.26 | 1656.96 | |
| **9** | **bengramling (4) — MY TEAM** | **4-10** | **1461.64** | **1678.36** | **Worst record AND lowest PF in the league** |
| 10 | cmgaither43 (1) | 6-8 | 1633.42 | 1670.26 | |
| 11 | Jukinski (3) | 6-8 | 1472.58 | 1643.84 | |
| 12 | ronakpatel32 (12) | 5-9 | 1645.32 | 1719.66 | |

Playoff bracket detail (winners, seeds 1–6 = rosters 7,11,6,2,10,5): R1: 6 beat 10, 2 beat 5. Semis: 6 beat 7, 2 beat 11. Final: **2 beat 6**. 3rd place: 7 beat 11. 5th: 10 beat 5. Consolation: 8 beat 9 for 7th; 4 beat 1 for 9th; 3 beat 12 for 11th.

**MY TEAM context:** last in points, last in record, but won the 9th-place consolation game and holds the **1.01** in the 2026 rookie draft. Classic rebuild position.

## 5. Full 2026 rosters (as of 2026-07-26; NFL teams/ages from Sleeper dump — reflect 2026 offseason movement)

### Roster 4 — bengramling — MY TEAM (21 players: 19 active, 0 IR, 2 taxi)
- **QB (2):** Joe Burrow (CIN, 29), Joe Flacco (CIN, 41)
- **RB (6):** Ashton Jeanty (LV, 22), Omarion Hampton (LAC, 23), Kenneth Walker (KC, 25), Javonte Williams (DAL, 26), Tyler Allgeier (ARI, 26), Rico Dowdle (PIT, 28)
- **WR (8):** Travis Hunter (JAX, 23), Jordan Addison (MIN, 24), Tank Dell (HOU, 26), Chris Godwin (TB, 30), Courtland Sutton (DEN, 30), Mike Evans (SF, 32), Stefon Diggs (FA, 32), Alec Pierce (IND, 26)
- **TE (3):** Sam LaPorta (DET, 25), Theo Johnson (NYG, 25), Darren Waller (FA, 33)
- **TAXI:** Cam Ward QB (TEN, 24), Elijah Arroyo TE (SEA, 23)
- Shape: young elite RB duo (Jeanty/Hampton) + Burrow + aging WR depth. Avg active age 27.7 — **oldest roster in the league**.

### Roster 1 — cmgaither43 (21: 19 active, 2 taxi)
- QB (5): Jayden Daniels (WAS, 25), J.J. McCarthy (MIN, 23), Geno Smith (NYJ, 35), Jacoby Brissett (ARI, 33), Malik Willis (MIA, 27)
- RB (5): TreVeyon Henderson (NE, 23), Chase Brown (CIN, 26), D'Andre Swift (CHI, 27), Chris Rodriguez (JAX, 26), George Holani (SEA, 26)
- WR (6): Drake London (ATL, 25), Rome Odunze (CHI, 24), Adonai Mitchell (NYJ, 23), Dontayvion Wicks (PHI, 25), Jerry Jeudy (CLE, 27), Parker Washington (JAX, 24)
- TE (3): Brock Bowers (LV, 23), Isaiah Likely (NYG, 26), Juwan Johnson (NO, 29)
- TAXI: Jordan James RB (SF, 22), KeAndre Lambert-Smith WR (LAC, 24)

### Roster 2 — jaketoppen (20: 18 active, 2 IR) — defending champ
- QB (2): C.J. Stroud (HOU, 24), Jared Goff (DET, 31)
- RB (7): Jahmyr Gibbs (DET, 24), Derrick Henry (BAL, 32), James Conner (ARI, 31), Aaron Jones (MIN, 31), Isiah Pacheco (DET, 27), Jordan Mason (MIN, 27), Travis Etienne (NO, 27)
- WR (6): Nico Collins (HOU, 27), Josh Downs (IND, 24), Christian Kirk (SF, 29), Darnell Mooney (NYG, 28), Marquise Brown (PHI, 29), Malik Washington (MIA, 25)
- TE (3): Trey McBride (ARI, 26), Pat Freiermuth (PIT, 27), Michael Mayer (LV, 25)
- IR: Daniel Jones QB (IND, 29), George Kittle TE (SF, 32)

### Roster 3 — Jukinski (23: 20 active, 1 IR, 2 taxi)
- QB (2): Caleb Williams (CHI, 24), Trevor Lawrence (JAX, 26)
- RB (5): Alvin Kamara (NO, 31), Tyjae Spears (TEN, 25), Kendre Miller (NO, 24), Rachaad White (WAS, 27), Devin Singletary (NYG, 28)
- WR (9): Puka Nacua (LAR, 25), Marvin Harrison (ARI, 23), DK Metcalf (PIT, 28), Xavier Worthy (KC, 23), Rashid Shaheed (SEA, 27), Troy Franklin (DEN, 23), Kyle Williams (NE, 23), Jalin Hyatt (NYG, 24), DeMario Douglas (NE, 25)
- TE (4): Jake Ferguson (DAL, 27), Cole Kmet (CHI, 27), David Njoku (LAC, 30), Dalton Schultz (HOU, 30)
- IR: Zach Charbonnet RB (SEA, 25) · TAXI: Kalel Mullings RB (TEN, 23), Tez Johnson WR (TB, 24)

### Roster 5 — trdouglas (22: 20 active, 2 taxi)
- QB (3): Justin Herbert (LAC, 28), Jordan Love (GB, 27), Tyler Shough (NO, 26)
- RB (4): Bijan Robinson (ATL, 24), Jonathan Taylor (IND, 27), Audric Estime (NO, 22), Sean Tucker (TB, 24)
- WR (10): Khalil Shakir (BUF, 26), Matthew Golden (GB, 22), Cooper Kupp (SEA, 33), Tre' Harris (LAC, 24), Christian Watson (GB, 27), Cedric Tillman (CLE, 26), Jalen Coker (CAR, 24), Tre Tucker (LV, 25), Luke McCaffrey (WAS, 25), Konata Mumpfield (LAR, 23)
- TE (3): Tyler Warren (IND, 24), AJ Barner (SEA, 24), Brenton Strange (JAX, 25)
- TAXI: Jalen Milroe QB (SEA, 23), DJ Giddens RB (IND, 22)

### Roster 6 — millj (22: 19 active, 3 taxi) — 2025 runner-up
- QB (3): Jalen Hurts (PHI, 27), Justin Fields (KC, 27), Sam Darnold (SEA, 29)
- RB (7): Saquon Barkley (PHI, 29), Christian McCaffrey (SF, 30), Cam Skattebo (NYG, 24), J.K. Dobbins (DEN, 27), Brian Robinson (ATL, 27), Tyrone Tracy (NYG, 26), MarShawn Lloyd (GB, 25)
- WR (7): Brian Thomas (JAX, 23), Ladd McConkey (LAC, 24), DJ Moore (BUF, 29), Jauan Jennings (MIN, 29), Savion Williams (GB, 24), Jalen Nailor (LV, 27), Jalen Tolbert (MIA, 27)
- TE (2): Harold Fannin (CLE, 22), Dallas Goedert (PHI, 31)
- TAXI: LeQuint Allen RB (JAX, 21), Jack Bech WR (LV, 23), Jayden Higgins WR (HOU, 23)

### Roster 7 — joeydavis299 (22: 19 active, 3 taxi) — best 2025 record (11-3)
- QB (4): Baker Mayfield (TB, 31), Bryce Young (CAR, 25), Michael Penix (ATL, 26), Matthew Stafford (LAR, 38)
- RB (6): Breece Hall (NYJ, 25), RJ Harvey (DEN, 25), Braelon Allen (NYJ, 22), Jonathon Brooks (CAR, 23), Jaylen Wright (MIA, 23), Keaton Mitchell (LAC, 24)
- WR (6): Ja'Marr Chase (CIN, 26), Jaxon Smith-Njigba (SEA, 24), Brandon Aiyuk (SF, 28), Davante Adams (LAR, 33), Jayden Reed (GB, 26), Andrei Iosivas (CIN, 26)
- TE (3): Colston Loveland (CHI, 22), Mark Andrews (BAL, 30), Travis Kelce (KC, 36)
- TAXI: Ollie Gordon RB (MIA, 22), Trevor Etienne RB (CAR, 22), Isaiah Bond WR (CLE, 22)

### Roster 8 — vishan (20: 19 active, 1 taxi) — youngest roster (avg 24.2)
- QB (2): Josh Allen (BUF, 30), Jaxson Dart (NYG, 23)
- RB (5): Chuba Hubbard (CAR, 27), Dylan Sampson (CLE, 21), Woody Marks (HOU, 25), Jacory Croskey-Merritt (WAS, 25), Jaydon Blue (DAL, 22)
- WR (7): Malik Nabers (NYG, 22), Keon Coleman (BUF, 23), Tory Horton (SEA, 23), Chimere Dike (TEN, 24), Isaac TeSlaa (DET, 24), Kayshon Boutte (NE, 24), Pat Bryant (DEN, 23)
- TE (5): Kyle Pitts (ATL, 25), Evan Engram (DEN, 31), Mason Taylor (NYJ, 22), Gunnar Helm (TEN, 23), Terrance Ferguson (LAR, 23)
- TAXI: Shedeur Sanders QB (CLE, 24)

### Roster 9 — josbaski (20: 17 active, 3 taxi)
- QB (4): Bo Nix (DEN, 26), Tua Tagovailoa (ATL, 28), Mac Jones (SF, 27), Tyson Bagent (CHI, 26)
- RB (4): James Cook (BUF, 26), Najee Harris (FA, 27), Quinshon Judkins (CLE, 22), Trey Benson (ARI, 24)
- WR (8): Justin Jefferson (MIN, 27), A.J. Brown (NE, 29), Tetairoa McMillan (CAR, 23), Xavier Legette (CAR, 25), Jalen McMillan (TB, 24), Keenan Allen (FA, 33), Devaughn Vele (NO, 28), Ryan Flournoy (DAL, 26)
- TE (1): T.J. Hockenson (MIN, 29)
- TAXI: Dont'e Thornton WR (LV, 23), Elic Ayomanor WR (TEN, 23), Jimmy Horn WR (CAR, 23)
- Note: raw data shows both Quinshon Judkins on roster 9 and Dylan Sampson on roster 8 — Judkins is on **roster 9 (josbaski)**.

### Roster 10 — NoahMoell (20: 19 active, 1 taxi)
- QB (3): Patrick Mahomes (KC, 30), Brock Purdy (SF, 26), Kyler Murray (MIN, 28)
- RB (6): Bucky Irving (TB, 23), Josh Jacobs (GB, 28), David Montgomery (HOU, 29), Tank Bigsby (PHI, 23), Ray Davis (BUF, 26), Kenny Gainwell (TB, 27)
- WR (8): CeeDee Lamb (DAL, 27), Garrett Wilson (NYJ, 26), Rashee Rice (KC, 26), DeVonta Smith (PHI, 27), Luther Burden (CHI, 22), Deebo Samuel (FA, 30), Quentin Johnston (LAC, 24), Romeo Doubs (NE, 26)
- TE (2): Tucker Kraft (GB, 25), Chig Okonkwo (WAS, 26)
- TAXI: Jaylin Noel WR (HOU, 23)

### Roster 11 — DrewR87 (22: 19 active, 3 taxi) — 2025 top scorer
- QB (2): Drake Maye (NE, 23), Dak Prescott (DAL, 32)
- RB (7): De'Von Achane (MIA, 24), Kyren Williams (LAR, 25), Kaleb Johnson (PIT, 22), Bhayshul Tuten (JAX, 23), Blake Corum (LAR, 25), Kimani Vidal (LAC, 24), Devin Neal (NO, 22)
- WR (8): Amon-Ra St. Brown (DET, 26), Tee Higgins (CIN, 27), George Pickens (DAL, 25), Jaylen Waddle (DEN, 27), Tyreek Hill (FA, 31), Marvin Mims (DEN, 24), Jakobi Meyers (JAX, 29), Michael Wilson (ARI, 26)
- TE (2): Dalton Kincaid (BUF, 26), Cade Otton (TB, 27)
- TAXI: Phil Mafah RB (DAL, 23), Arian Smith WR (NYJ, 24), Efton Chism WR (NE, 24)

### Roster 12 — ronakpatel32 (18 active, no IR/taxi — thinnest roster)
- QB (2): Lamar Jackson (BAL, 29), Riley Leonard (IND, 23)
- RB (4): Jaylen Warren (PIT, 27), Tony Pollard (TEN, 29), Rhamondre Stevenson (NE, 28), Kyle Monangai (CHI, 24)
- WR (9): Emeka Egbuka (TB, 23), Chris Olave (NO, 26), Jameson Williams (DET, 25), Zay Flowers (BAL, 25), Terry McLaurin (WAS, 30), Michael Pittman (PIT, 28), Ricky Pearsall (SF, 25), Rashod Bateman (BAL, 26), Wan'Dale Robinson (TEN, 25)
- TE (3): Oronde Gadsden (LAC, 23), Hunter Henry (NE, 31), Jake Tonges (SF, 27)

### Roster shape summary (active players only)

| Roster | Team | QB | RB | WR | TE | Avg age |
|---|---|---|---|---|---|---|
| 1 | cmgaither43 | 5 | 5 | 6 | 3 | 26.2 |
| 2 | jaketoppen | 2 | 7 | 6 | 3 | 27.4 |
| 3 | Jukinski | 2 | 5 | 9 | 4 | 26.0 |
| 4 | **bengramling** | 2 | 6 | 8 | 3 | **27.7 (oldest)** |
| 5 | trdouglas | 3 | 4 | 10 | 3 | 25.3 |
| 6 | millj | 3 | 7 | 7 | 2 | 26.7 |
| 7 | joeydavis299 | 4 | 6 | 6 | 3 | 27.0 |
| 8 | vishan | 2 | 5 | 7 | 5 | **24.2 (youngest)** |
| 9 | josbaski | 4 | 4 | 8 | 1 | 26.5 |
| 10 | NoahMoell | 3 | 6 | 8 | 2 | 26.3 |
| 11 | DrewR87 | 2 | 7 | 8 | 2 | 25.7 |
| 12 | ronakpatel32 | 2 | 4 | 9 | 3 | 26.3 |

## 6. Draft pick ownership (from 2026-league `traded_picks`, 36 traded picks; base = 4 rounds/year × 12 teams)

2026 pick numbers use the set linear draft order (slot repeats every round). "(from X)" = acquired pick; picks not listed as traded are held by the original team. **No 2028 picks have been traded — every team holds its own full 2028 set (R1–R4).**

| Team | 2026 picks | 2027 picks |
|---|---|---|
| **bengramling (4)** | **1.01, 2.09 (from DrewR87), 3.03 (from ronakpatel32), 4.01** — own 2.x is gone (to millj via ronakpatel32), own 3.x gone (to cmgaither43 via ronakpatel32) | Own R1, R2, R4 (own R3 → DrewR87) |
| cmgaither43 (1) | 1.04 (from Jukinski), 2.11 (from millj), 3.01 (from bengramling), 3.07 (from trdouglas) — own 1.06→Jukinski, own 2.06→trdouglas, own 3.06→millj, own 4.06→ronakpatel32 | Own R1, R2, +R2 (from trdouglas), R4 (own R3 → trdouglas) |
| jaketoppen (2) | Only 2.12, 3.12 — own 1.12→Jukinski, own 4.12→NoahMoell | Own R1 + R1 (from vishan) + R2 (from Jukinski) + R4 (own R2→josbaski, own R3→vishan) |
| Jukinski (3) | 1.06 (from cmgaither43), 1.12 (from jaketoppen), 2.04, 4.04 — own 1.04→cmgaither43, own 3.04→millj | Own R1, R3, R4 + R2 (from millj) (own R2 → jaketoppen) |
| trdouglas (5) | 1.07, 1.08 (from NoahMoell), 2.06 (from cmgaither43), 2.07, 4.07, 4.11 (from millj) — own 3.07→cmgaither43 | Own R1 + R1 (from NoahMoell) + own R3 + R3 (from cmgaither43) + R4 (own R2 → cmgaither43) |
| millj (6) | 1.03 (from ronakpatel32), 2.01 (from bengramling), 3.04 (from Jukinski), 3.06 (from cmgaither43), 4.02 (from vishan), 4.03 (from ronakpatel32) — own 1.11→DrewR87, own 2.11→cmgaither43, own 3.11→NoahMoell, own 4.11→trdouglas | Own R3, R4 + R4 (from vishan) + R4 (from ronakpatel32) — own R1→vishan, own R2→Jukinski |
| joeydavis299 (7) | Full own set: 1.10, 2.10, 3.10, 4.10 | Full own set R1–R4 |
| vishan (8) | 1.02, 2.02, 3.02, 4.09 (from DrewR87) — own 4.02→millj | R1 (from millj), own R2, own R3 + R3 (from jaketoppen) — own R1→jaketoppen, own R4→millj |
| josbaski (9) | Full own set: 1.05, 2.05, 3.05, 4.05 | Own R1–R4 + R2 (from jaketoppen) — **5 picks** |
| NoahMoell (10) | 2.08, 3.08, 3.11 (from millj), 4.08, 4.12 (from jaketoppen) — own 1.08→trdouglas | Own R2, R3, R4 — own R1→trdouglas |
| DrewR87 (11) | 1.09, 1.11 (from millj), 3.09 — own 2.09→bengramling, own 4.09→vishan | Own R1, R2, R3, R4 + R3 (from bengramling) — **5 picks** |
| ronakpatel32 (12) | Only 2.03, 4.06 (from cmgaither43) — own 1.03→millj, own 3.03→bengramling, own 4.03→millj | Own R1, R2, R3 — own R4→millj |

Sanity check: 48 picks accounted for in each of 2026 and 2027.

## 7. 2026 rookie draft (draft_id 1327016687945392128)

- **Status:** pre_draft. **Type: `linear`** (NOT snake — same order all 4 rounds). **4 rounds.** `player_type = 1` (rookies only). Scheduled `start_time = 1786806059000` ≈ **Aug 15, 2026**.
- **Draft order is SET** (appears to be inverse of 2025 finish with the two finalists picking 11/12):

| Slot | Team | Slot | Team |
|---|---|---|---|
| 1 | **bengramling (MY TEAM — the 1.01)** | 7 | trdouglas |
| 2 | vishan | 8 | NoahMoell |
| 3 | ronakpatel32 | 9 | DrewR87 |
| 4 | Jukinski | 10 | joeydavis299 |
| 5 | josbaski | 11 | millj (runner-up) |
| 6 | cmgaither43 | 12 | jaketoppen (champion) |

- 2025 startup draft (draft_id 1251359015015809024): completed 2025-07-21, **snake, 22 rounds**, all players (`player_type = 0`) — this league is only one year old (2025 league has `previous_league_id = None`).

## 8. Market behavior — 2025 transaction history (weeks 1–18 of league 1251359014202114048)

**201 completed transactions: 114 waiver claims, 61 free-agent moves, 26 trades.** 127 total adds and 127 drops. Last trades executed 2025-11-17 (week 11 deadline held).

### FAAB / waivers (2025 budget was $200/team; 2026 budget is $50)
- Total FAAB spent: **$1,591 of $2,400** league-wide.
- Winning-bid distribution: **$0 × 48, $1–5 × 20, $6–20 × 18, $21–50 × 18, $51+ × 10**. Median winning bid is low — most claims are uncontested.
- Biggest bids: **$126 Emari Demercado (josbaski, wk5)**, $115 Kyler Murray (NoahMoell, wk11), $75 LeQuint Allen (cmgaither43, wk1), $68 David Njoku (jaketoppen, wk14), $61 Hassan Haskins (DrewR87), $60 × 3 (Devaughn Vele, Kimani Vidal, **Darren Waller — bengramling wk4**), $56 Dawson Knox, $53 Sean Tucker.
- FAAB spent by team (= `waiver_budget_used`): millj 200, cmgaither43 200, josbaski 196, **bengramling 191**, trdouglas 183, NoahMoell 163, DrewR87 160, jaketoppen 114, joeydavis299 77, ronakpatel32 62, Jukinski 30, vishan 15.
- Add volume by team (waiver+FA): millj 21, cmgaither43 21, josbaski 14, trdouglas 12, DrewR87 11, NoahMoell 11, joeydavis299 10, ronakpatel32 9, jaketoppen 6, bengramling 5, Jukinski 5, vishan 2.

### Trades (26 in 2025)
Twelve trades in the "week 1" window were mostly startup-adjacent pick swaps (Jul 20–23, 2025). Notable in-season deals:
- wk4: Jukinski sent Travis Etienne + kept-side detail → **got jaketoppen's 2026 R1 (became 1.12)** for Etienne + a 2026 R3.
- wk5: **bengramling got Courtland Sutton + Justin Fields from millj for Cam Skattebo** (Skattebo became millj's cornerstone RB).
- wk10 blockbuster: millj got **Saquon Barkley** + Jack Bech + vishan's 2026 R4 + 2027 R4; vishan got Dylan Sampson + Evan Engram + **millj's 2026 R1 + 2027 R1** (vishan tearing down for picks).
- wk10: trdouglas got Tre Tucker + **NoahMoell's 2026 R1 + 2027 R1**; NoahMoell got **Bucky Irving + Luther Burden** (win-now consolidation).
- wk11 (deadline day): cmgaither43 got **Jayden Daniels** for **Derrick Henry + C.J. Stroud**; jaketoppen got **Nico Collins + vishan's 2027 R1** for **Malik Nabers** + a 2027 R3; jaketoppen got Goff + Aaron Jones from josbaski for a 2027 R2.
- MY TEAM (bengramling) 2025 trade activity: mostly startup pick swaps + the Skattebo→Sutton/Fields deal. Traded away: own 2026 R2 (to DrewR87→…), own 2026 R3, own 2027 R3; acquired DrewR87's 2026 R2, ronakpatel32's 2026 R3.

### 2026 offseason activity so far (league 1312124603224555520, leg 1)
**65 completed transactions: 30 waiver claims ($161 total), 28 free-agent moves, 7 trades.** Offseason FAAB already spent (of $50): **cmgaither43 50, jaketoppen 50, millj 50** (all tapped out until any budget trade), josbaski 6, ronakpatel32 5, everyone else 0. Max bids: $50 Isiah Pacheco (jaketoppen), $50 Malik Willis (cmgaither43), $40 MarShawn Lloyd (millj).
Offseason trades: jaketoppen got **Jahmyr Gibbs** for Pearsall + Egbuka + Swift + a 2026 R3 (2026-01-09); cmgaither43 got **Brock Bowers + TreVeyon Henderson + Jukinski's 2026 R1** for Kamara + Nacua + Downs + cmgaither43's own 2026 R1 (2026-01-04); millj got ronakpatel32's 2026 R1 (1.03) + a 3rd for Jameson Williams + Parker Washington (2026-02-01); jaketoppen got DJ Moore for millj's 2027 R2 (later flipped to Jukinski with Njoku for Josh Downs, 2026-05-21); cmgaither43↔ronakpatel32 swap (Swift/P.Washington/ben's-2026-R3 for Gadsden/Wan'Dale/4th, 2026-04-11).

### Market takeaways for the bot
1. **Active trade market**: 33 trades in ~12 months across 12 teams; picks (especially R1s) move constantly; instant processing, no effective veto friction.
2. **FAAB is now scarce** ($50 vs $200): 2025 bid levels ÷ 4 is the right prior; three teams already have $0 for the entire 2026 season, a real competitive edge for teams with budget left (bengramling has full $50).
3. Most waiver claims are $0–5; real bidding wars happen for streaming QBs/TEs and suddenly-relevant RBs.
4. Rebuilders (vishan 2025) successfully converted vets → future R1s; contenders (NoahMoell, jaketoppen, millj) paid picks for immediate starters.

## 9. Facts most relevant to the scoring system

1. Value baseline: **1QB (use KTC 1QB values, not superflex), full PPR, no TE premium, 4-pt pass TD.**
2. Lineup demand per team: 1 QB, 2–4 RB, 3–5 WR, 1–3 TE (2 FLEX). League-wide weekly starter demand: 12 QB, 24–48 RB, 36–60 WR, 12–36 TE.
3. Roster limit 19 active + 3 taxi (vets allowed) + 2 IR (OUT-only). Bench is deep (10), so stashes are viable.
4. MY TEAM (roster 4) = worst 2025 team, lowest PF, oldest roster, but owns **2026 1.01 + 4.01 + 2.09 + 3.03** and Jeanty/Hampton/Burrow/Hunter/LaPorta young core vs aging WR room (Evans/Diggs/Godwin/Sutton 30+). Positional need skews young WR; tradeable surplus is veteran WRs.
5. Trade deadline week 11; playoffs weeks 15–17, 6 teams, top-2 byes; 14-game regular season, no divisions.
6. 2026 rookie draft is **linear**, so the 1.01 team also gets 2.01-equivalent leverage at 25th overall (bengramling picks 1st AND 37th... precisely: picks 1, 25th? no — linear means slot 1 picks 1st, 13th, 25th, 37th if holding own picks; bengramling holds 1.01, 2.09 (=pick 21), 3.03 (=pick 27), 4.01 (=pick 37)).

## 10. Raw file locations (scratchpad)

All under `/tmp/claude-1000/-home-bgram-dev-dynasty-bot/9d23798c-22b9-434a-b902-71d156ef37bd/scratchpad/`: `players_nfl.json`, `league26.json`, `league25.json`, `users26.json`, `users25.json`, `rosters26.json`, `rosters25.json`, `picks26.json`, `picks25.json`, `drafts26.json`, `drafts25.json`, `wb25.json`, `lb25.json`, `tx25_w1.json` … `tx25_w18.json`, `tx26_w1.json`.
