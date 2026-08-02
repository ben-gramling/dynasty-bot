# Sleeper API Reference for dynasty-bot

Verified live on 2026-07-26 against the real Chicago Dynasty league. All endpoints below were exercised with `curl` unless noted.

## 0. Ground rules (verified)

- **Base URL:** `https://api.sleeper.app/v1` (avatars are on `https://sleepercdn.com`).
- **No authentication.** The API is read-only; no token, no API key, no write operations exist.
- **Rate limit:** docs say stay **under 1000 API calls per minute** or risk an IP block. Error codes: 400, 404, 429 (too many requests), 500, 503.
- **No pagination anywhere.** Every endpoint returns the complete array/object in one response. Transactions are segmented by week ("round"/leg), not paginated.
- **CORS is wide open** (verified header: `access-control-allow-origin: *`, `access-control-allow-credentials: true`), so the browser could call the API directly — but responses are CDN-cached (`cache-control: public, s-maxage=60, stale-while-revalidate=180, stale-if-error=600`, Cloudflare), so data can be up to ~60s stale. For dynasty-bot, server-side fetching in the daily cron is still preferred.
- **Error semantics gotcha (verified):** a bad `league_id` returns HTTP **404 with body `null`**, but an unknown **username returns HTTP 200 with body `null`**. Always null-check user lookups; status code alone is not enough.
- **IDs are strings** in most places (`user_id`, `league_id`, `draft_id`, `player_id`), but `roster_id` is an **int**, and in draft traded-picks the `draft_id` comes back as a **number** (type inconsistency — normalize to string in our code).
- `username` can change; **store `user_id`** (docs' explicit guidance).

## 1. Verified real IDs (Chicago Dynasty)

| Entity | Value |
|---|---|
| Sleeper username | `bengramling` (display_name `bengramling`, avatar `null`) |
| user_id | `1095425159290331136` |
| 2026 league_id (current, status `pre_draft`) | `1312124603224555520` |
| 2025 league_id (previous, status `complete`) | `1251359014202114048` |
| 2026 rookie draft_id | `1327016687945392128` (linear, 4 rounds, `player_type: 1` = rookies only, starts 2026‑08‑15, status `pre_draft`) |
| User's roster_id | **4** in both 2025 and 2026 (roster_ids persist across season rollover) |
| Team name (users metadata) | "what would it take" |
| League shape | 12 teams, dynasty (`settings.type = 2`), 1QB: `[QB, RB, RB, WR, WR, WR, TE, FLEX, FLEX]` + 10 BN, `reserve_slots: 2` (IR), `taxi_slots: 3` (`taxi_allow_vets: 1`, `taxi_years: 1`, `taxi_deadline: 4`) |
| Scoring | Full PPR (`rec: 1.0`), `pass_td: 4.0`, `pass_yd: 0.04`, `rush_yd/rec_yd: 0.1`, no TE premium (`bonus_rec_te` absent); 43 scoring keys total |
| Waivers | FAAB (`waiver_type: 2`), budget **$50**, `daily_waivers: 1`, `waiver_clear_days: 1`, `waiver_bid_min` null/0 |
| Trades | `pick_trading: 1`, `trade_deadline: 11` (week), `trade_review_days: 0`, `veto_votes_needed: 6` |
| Playoffs | 6 teams (`playoff_teams: 6`), start week 15 (`playoff_week_start: 15`) |
| Rookie draft rounds | `settings.draft_rounds: 4` |

This is the user's **only** 2026 league (leagues endpoint returned exactly 1). Caution: a different Sleeper account `bgram` (user_id `729166377545469952`) exists and is **not** this user — matching on username guesses is dangerous; always confirm via league membership.

## 2. Endpoint catalog

### 2.1 User lookup
```
GET https://api.sleeper.app/v1/user/<username>
GET https://api.sleeper.app/v1/user/<user_id>
```
- Returns a single user object. Docs show only `{username, user_id, display_name, avatar}`; **reality has ~20 fields**, the extras (`email`, `phone`, `real_name`, `cookies`, `token`, `verification`, `created`, …) all `null` for other users, plus `is_bot: false`.
- Fields we rely on: `user_id`, `username`, `display_name`, `avatar`.
- Unknown username → **200 + `null` body** (verified).
- **Used by:** onboarding/config (resolve username → user_id), all tabs indirectly.

### 2.2 User leagues
```
GET https://api.sleeper.app/v1/user/<user_id>/leagues/<sport>/<season>
```
e.g. `/v1/user/1095425159290331136/leagues/nfl/2026`. `sport` is always `nfl`; `season` is a year string.
- Returns an array of full league objects (same shape as §2.3).
- **Used by:** onboarding (find the league each new season after rollover), daily cron (detect the new-season league via `previous_league_id` chain).

### 2.3 League
```
GET https://api.sleeper.app/v1/league/<league_id>
```
Key fields (all verified):
- `name`, `status` (`pre_draft` | `drafting` | `in_season` | `complete`), `season` ("2026"), `season_type`, `sport`, `total_rosters` (12), `previous_league_id`, `draft_id`, `avatar`.
- `roster_positions`: ordered array of starting slots + `"BN"` entries — this is the source of truth for lineup requirements (drives positional-need math). No `SUPER_FLEX` present ⇒ 1QB league.
- `scoring_settings`: flat map of stat → points (`rec: 1.0` ⇒ PPR).
- `settings`: ~45 keys; the ones that matter for roster decisions: `type` (2 = dynasty), `max_keepers`, `taxi_slots`/`taxi_allow_vets`/`taxi_years`/`taxi_deadline`, `reserve_slots`, `waiver_type` (2 = FAAB), `waiver_budget`, `daily_waivers`, `waiver_clear_days`, `waiver_day_of_week`, `pick_trading`, `trade_deadline`, `draft_rounds`, `playoff_teams`, `playoff_week_start`, `num_teams`, `best_ball`, `disable_trades`, `disable_adds`, `leg` (current week).
- Extra live fields not in docs: `metadata`, `shard`, `group_id`, `bracket_id`, `loser_bracket_id`, various `last_message_*`/`last_author_*` chat fields.
- **Used by:** all tabs (league config), league strength tab (roster requirements), waiver tab (FAAB rules), trades tab (deadline, pick trading).

### 2.4 League rosters
```
GET https://api.sleeper.app/v1/league/<league_id>/rosters
```
Returns 12 roster objects:
- `roster_id` (int, 1–12, **stable across seasons**), `owner_id` (user_id string), `league_id`.
- `players`: all player_ids on roster (our user: 21). `starters`: ordered player_id list matching `roster_positions` (carries over from last set lineup even in pre_draft; can contain `"0"` for empty slots in other leagues).
- `reserve`: IR list or `null`. `taxi`: taxi-squad list or `null` (our user: `["12521","12522"]` — 2 of 3 slots used). `keepers`: `null` here (used in keeper leagues). `co_owners`, `metadata`, `player_map` — extra fields not in docs (usually `null`).
- `settings`: `wins/losses/ties`, `fpts` (+ `fpts_decimal`: true value = `fpts + fpts_decimal/100`), `fpts_against(_decimal)`, `ppts(_decimal)` = **potential points (max possible) — great for league-strength "manager efficiency"**, `waiver_position`, `waiver_budget_used` (FAAB spent), `total_moves`. **Offseason gotcha:** the fresh 2026 league's roster settings contain only `{fpts, losses, ties, total_moves, waiver_budget_used, waiver_position, wins}` — `fpts_against`/`ppts`/decimals appear only after games are played; a `locked` key appears sometimes. Read all point fields defensively.
- 2025 final for our user (roster_id 4): 4–10, 1461.64 fpts, 1838.64 ppts, 1678.36 fpts_against.
- **Used by:** league strength tab (per-team KTC totals, records, ppts efficiency), trades tab (all rosters' assets), waiver tab (who owns whom; FAAB budgets used).

### 2.5 League users
```
GET https://api.sleeper.app/v1/league/<league_id>/users
```
- 12 objects: `user_id`, `display_name`, `avatar`, `metadata.team_name` (e.g. "what would it take"), `is_owner` (= commissioner flag; multiple allowed), plus undocumented `is_bot`, `league_id`, `settings`.
- **Docs-vs-reality:** docs show a `username` field — **it is NOT present** in the live response. Map rosters→people via `roster.owner_id` → `user.user_id`, display via `display_name`/`metadata.team_name`.
- **Used by:** league strength tab and trades tab (label teams with human names).

### 2.6 Matchups (per week)
```
GET https://api.sleeper.app/v1/league/<league_id>/matchups/<week>
```
- One object per team (12 rows); pairs share `matchup_id`. Fields: `roster_id`, `matchup_id`, `starters`, `players`, `points`, `custom_points` (commissioner override, normally null).
- **Undocumented bonus fields (verified):** `starters_points` (ordered list aligned with `starters`) and `players_points` (map player_id → points for everyone on the roster that week). These give per-player weekly fantasy production without any stats endpoint — key input for "roster strength" and buy-low/sell-high signals.
- Offseason/pre-draft or out-of-range week → `[]` with HTTP 200 (verified: 2026 week 1 → `[]`, week 25 → `[]`).
- **Used by:** league strength tab (2025 weekly scoring history, weeks 1–17), trades tab (production trends).

### 2.7 Playoff brackets
```
GET https://api.sleeper.app/v1/league/<league_id>/winners_bracket
GET https://api.sleeper.app/v1/league/<league_id>/losers_bracket
```
(Docs contain a typo `loses_bracket` in one spot; the real path is `losers_bracket`.)
- Rows: `{r: round, m: match id, t1, t2: roster_ids or null, w, l: winning/losing roster_id, t1_from/t2_from: {w: m}|{l: m}, p: placement}`. `p: 1` = championship, `p: 3` = 3rd-place, `p: 5` = 5th-place game.
- Verified 2025 CD: winners bracket 7 rows (6-team playoff), champion = roster_id **2**; losers bracket 7 rows. Empty/next-season league → may be small or empty.
- **Used by:** league strength tab (final finishes; win-now vs rebuild context for each franchise).

### 2.8 Transactions (per week/"round")
```
GET https://api.sleeper.app/v1/league/<league_id>/transactions/<round>
```
`round` = NFL week ("leg"). **All offseason activity lands in round 1** (verified: the pre-draft 2026 league already had **70 transactions in round 1**: 28 free_agent, 35 waiver, 7 trades). Round 0 → `[]`; weeks with no activity → `[]` (2025 week 18 had 0).
- Common fields: `transaction_id`, `type` (`trade` | `waiver` | `free_agent`), `status` (`complete` | `failed`), `status_updated`, `created` (ms epoch), `creator` (user_id), `roster_ids`, `consenter_ids`, `leg`, `metadata`, `settings`.
- `adds` / `drops`: maps of player_id → roster_id (either can be null).
- Waivers: `settings: {waiver_bid: N, seq: n, priority?}` — **`waiver_bid` is the FAAB amount** (saw a $40 bid of the $50 budget). Failed claims keep `status: "failed"` with `metadata.notes` explaining why ("This player was claimed by another owner.", "…too many players after this transaction.") — failed bids are a market-price signal for the waiver tab.
- Trades: `draft_picks` array of `{season, round, roster_id (original owner), previous_owner_id, owner_id (new), league_id (extra, null)}`; `waiver_budget`: `[{sender, receiver, amount}]` for FAAB trades.
- Ordering (verified): sorted **descending by `created`** (not strictly by `status_updated`).
- **Used by:** trades tab (league trade history, market comps), waiver tab (FAAB price discovery), daily cron (poll round = current `leg`, plus round 1 in offseason).

### 2.9 Traded picks (league-level)
```
GET https://api.sleeper.app/v1/league/<league_id>/traded_picks
```
- All currently-traded picks incl. future seasons: `{season: "2026", round, roster_id (ORIGINAL owner), previous_owner_id, owner_id (current)}`. Verified: 36 rows covering seasons 2026 and 2027.
- To build each team's pick inventory: start with every (season, round, roster_id) for `draft_rounds` rounds × known future seasons, then apply these overrides. Picks NOT listed belong to their original roster.
- **Used by:** trades tab (pick assets & KTC pick values per team), league strength tab (future capital).

### 2.10 Drafts
```
GET https://api.sleeper.app/v1/user/<user_id>/drafts/<sport>/<season>   # all user drafts
GET https://api.sleeper.app/v1/league/<league_id>/drafts                # league drafts, newest first
GET https://api.sleeper.app/v1/draft/<draft_id>                         # one draft
GET https://api.sleeper.app/v1/draft/<draft_id>/picks                   # all picks
GET https://api.sleeper.app/v1/draft/<draft_id>/traded_picks            # pick trades scoped to that draft
```
- Draft object: `type` (`linear` | `snake` | `auction`), `status` (`pre_draft`/`complete`…), `start_time` (ms epoch), `season`, `league_id`, `draft_id`, `settings` (`rounds`, `pick_timer`, `player_type` — **1 = rookies-only**, slot counts, `reversal_round`), `metadata` (`scoring_type: "dynasty_ppr"`, `league_type: "2"`, name), `draft_order` (map user_id → draft slot; null before order set), and on the single-draft endpoint also `slot_to_roster_id` (map slot → roster_id). CD 2026: order already set, our slot = the map's entry for user 1095425159290331136.
- Picks (verified on a completed 2025 draft, 240 picks): `player_id`, `picked_by` (user_id, can be ""), `roster_id` (int — docs show string), `round`, `draft_slot`, `pick_no`, `is_keeper`, `draft_id`, undocumented `reactions`, and `metadata` (player snapshot: name, position, team, `injury_status`, `news_updated`, plus undocumented `team_abbr`, `team_changed_at`, `years_exp`).
- Draft traded_picks rows include an extra `draft_id` field **as a number**.
- **Used by:** trades tab (rookie-pick slot → KTC value once `slot_to_roster_id`/order known), daily cron (detect when the 2026-08-15 rookie draft completes to refresh rosters), league strength (draft capital).

### 2.11 Players — full dump
```
GET https://api.sleeper.app/v1/players/nfl
GET https://api.sleeper.app/v1/players/nfl?position=QB
GET https://api.sleeper.app/v1/players/nfl?active=true
GET https://api.sleeper.app/v1/players/nfl?position=QB&active=true
```
- **Docs mandate: call at most once per day** and cache server-side; docs say ~5MB but the live full dump is **14.6 MB raw JSON with 12,201 entries** (docs figure is outdated — budget accordingly; gzip helps).
- Keyed by player_id; **32 non-numeric keys are team DEFs** (`"CHI"`, `"DET"`, …).
- Fields we rely on: `player_id`, `first_name`/`last_name`/`full_name`, `position`, `fantasy_positions`, `team`, `age`, `years_exp`, `status` (`Active`/`Inactive`/`Injured Reserve`…), `injury_status`/`injury_body_part`/`injury_notes`, `depth_chart_position`/`depth_chart_order`, `number`, `search_rank` (999 = unranked), `news_updated` (ms epoch), `search_full_name` (normalized, good for KTC name matching), cross-IDs (`espn_id`, `yahoo_id`, `sportradar_id`, `gsis_id`, `rotowire_id`, `stats_id`, `fantasy_data_id`, plus newer `oddsjam_id`, `opta_id`, `kalshi_id`), `birth_date`, `height`, `weight`, `college`.
- Filtered variants are much smaller (verified: `?position=QB&active=true` → 355 entries, 434 KB) — but dynasty-bot needs all skill positions, so cache the full dump daily.
- Cached copy already exists at `/tmp/claude-1000/-home-bgram-dev-dynasty-bot/9d23798c-22b9-434a-b902-71d156ef37bd/scratchpad/players_nfl.json` (this session's scratchpad).
- **Used by:** daily cron (the once-per-day refresh); every tab reads from the cached map (player_id → name/pos/team/age for KTC joins and UI).

### 2.12 Trending players (waiver signal)
```
GET https://api.sleeper.app/v1/players/<sport>/trending/<type>?lookback_hours=<hours>&limit=<int>
```
- `type` = `add` | `drop`; `lookback_hours` default 24; `limit` default 25 (verified both params work; `lookback_hours=48` fine).
- Response: `[{player_id, count}]` — platform-wide add/drop counts (verified scale: top add had count 10,125 in 24h). Docs ask for attribution to Sleeper when displaying trending data.
- **Used by:** waiver tab (surface hot pickups the league hasn't rostered; cross-reference against league FA pool and KTC), daily cron (snapshot both add and drop lists).

### 2.13 NFL state
```
GET https://api.sleeper.app/v1/state/nfl
```
- Verified offseason response: `{week: 0, leg: 0, season: "2026", season_type: "off", previous_season: "2025", season_start_date: null, display_week: 0, league_season: "2026", league_create_season: "2026", season_has_scores: true}`. `season_has_scores` is undocumented. In-season, `season_type` ∈ `pre`/`regular`/`post`, `leg` = regular-season week, `display_week` may differ from `week`.
- **Used by:** daily cron (decide which week's matchups/transactions to pull; offseason vs in-season mode switching).

### 2.14 Avatars
```
https://sleepercdn.com/avatars/<avatar_id>          # full size (verified: 200, image/png, ~17KB)
https://sleepercdn.com/avatars/thumbs/<avatar_id>   # thumbnail (verified: 200, image/png, ~1.5KB)
```
- `avatar` ids appear on users and leagues; our user's avatar is `null` (render a fallback).
- **Used by:** all tabs (team/manager display).

## 3. Docs-vs-reality differences (all verified live)

1. **League users response has no `username` field** (docs show one). Use `display_name` + `metadata.team_name`.
2. **Matchups include `players_points` and `starters_points`** — undocumented and extremely useful (per-player weekly scoring).
3. **Full player dump is ~14.6 MB / 12,201 entries**, not the documented ~5 MB.
4. **Roster objects carry extra fields:** `taxi`, `keepers`, `co_owners`, `metadata`, `player_map`; roster `settings` includes undocumented `ppts`/`ppts_decimal` (potential points) and sometimes `locked`; offseason rosters omit `fpts_against`/decimals entirely.
5. **User object has ~16 undocumented (null) fields** plus `is_bot`.
6. **Unknown username → HTTP 200 `null`** (not 404); bad league_id → 404 `null`.
7. **Docs typo:** `loses_bracket` — the real path is `losers_bracket`.
8. **Draft picks:** `roster_id` is an int (docs show `"1"`); extra `reactions` field; pick `metadata` gains `team_abbr`, `team_changed_at`, `years_exp`. Draft traded-picks rows add `draft_id` as a **number**.
9. **Transaction trade `draft_picks` entries include `league_id: null`** (undocumented).
10. **Offseason behavior:** matchups → `[]`; all offseason transactions accumulate in round **1**; state shows `week: 0`, `season_type: "off"`, `season_start_date: null`; brackets from a completed league remain fully populated.
11. **State has undocumented `season_has_scores`.**
12. **Transactions are sorted descending by `created`.**
13. Players endpoint supports `?position=` and `?active=true` filters (documented on the page but easy to miss; verified working, e.g. QB+active = 355 players / 434 KB).

## 4. Feature → endpoint call plan

| Feature | Endpoints |
|---|---|
| **Daily data-collection cron** | `state/nfl` → decide mode; `players/nfl` (once/day, cache); `trending/add` + `trending/drop` snapshots; `league/<id>` (settings drift); `rosters`, `users`, `traded_picks`; `transactions/<current leg>` (offseason: round 1); `drafts`/`draft/<id>` until rookie draft completes, then `draft/<id>/picks` once |
| **Waiver tab** | cached players map + rosters (compute league FA pool = players not on any roster) + trending add/drop + transactions (FAAB bids incl. failed ones for price discovery) + league settings (FAAB budget $50, daily waivers) |
| **Trade CLI** (v7.1: no tab) | rosters + users + traded_picks + transactions (trade history) + draft `slot_to_roster_id` (pick slotting) + KTC values (external) |
| **League strength tab** | rosters (records, fpts, ppts) + users (names) + 2025 matchups weeks 1–17 (`players_points`) + winners/losers brackets (finishes) + traded_picks (future capital) |

Call-budget sanity check: a full daily refresh is ≈ 25 requests (1 players + 2 trending + 1 state + ~5 league-scoped + 17 weekly matchups on first backfill) — far below the 1000/min ceiling; only the players dump needs the once-per-day restraint.