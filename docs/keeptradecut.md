# KeepTradeCut Knowledge

Reverse-engineered documentation of KeepTradeCut (KTC) dynasty rankings, with a full dataset extraction performed 2026-07-26 as proof. All numbers below come from the actual extracted data, saved to `/home/bgram/dev/dynasty-bot/data/ktc_raw.json` (1.4 MB, 500 assets).

> **League context (dynasty-bot):** "Chicago Dynasty" is a 12-team, 1QB dynasty league (no SUPER_FLEX slot, no TE premium indicated). Therefore the correct KTC number for every asset is **`oneQBValues.value`** (the base value, NOT any `tep*` sub-object). Never use `superflexValues` — it inflates QBs by 13–41%.

---

## 1. Extraction method (verified working)

### Exactly what works

```bash
curl -sS -L \
  -A "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36" \
  -o ktc.html "https://keeptradecut.com/dynasty-rankings"
```

- Returns **HTTP 200, ~1.36 MB HTML**. No Cloudflare challenge, no cookies, no JS execution needed. Only a browser-ish `User-Agent` header is required (default curl UA untested; browser UA confirmed working).
- The complete dataset is embedded in an inline `<script>` as: **`var playersArray = [{...}, ...];`** — a single JSON array, directly parseable.

Parsing (Python):

```python
import re, json
html = open('ktc.html', encoding='utf-8').read()
m = re.search(r'var playersArray\s*=\s*(\[.*?\]);', html, re.DOTALL)
players = json.loads(m.group(1))   # 500 records
```

The non-greedy regex worked on the live page; a bracket-depth scanner is a safe fallback if `];` ever appears inside a string.

### Pagination: NOT needed — one page contains everything

Verified empirically: fetched both `https://keeptradecut.com/dynasty-rankings` and `https://keeptradecut.com/dynasty-rankings?page=1&filters=QB|WR|RB|TE|RDP&format=1`. Both embed a 500-element `playersArray` with **identical playerID sets (overlap 500/500, union 500)**. The `page`, `filters`, and `format` query params only affect client-side rendering (50 rows shown per page in the UI); the full array ships on every page load. **One request = complete dataset.**

- `format` semantics (display only): `1` = 1QB, `2` = Superflex (site default; `var formatCookie = 2`). Irrelevant for scraping because **both** `oneQBValues` and `superflexValues` objects are always present on every record.
- Other inline vars on the page: `oneQBPlayers` and `superflexPlayers` are tiny 3-item featured/trending lists (subsets of the 500 — ignore); `lastProcessedTimes = {"OneQB":"4 minutes ago","Superflex":"4 minutes ago"}` (update-cadence evidence); `filteredPlayersIds`, `leagueType`, cookie helpers.

### Dataset boundary caveat

The 500 embedded assets are the **top 500 by Superflex value** (superflex ranks are exactly 1–500 contiguous). `oneQBValues.rank` inside the set runs 1–743 with gaps, because KTC ranks a larger internal pool. Missing 1QB ranks under 500: only 15, all deep bench-fodder ranks (462, 463, 471, 473, 475, 476, 477, 480, 483, 488, 490, 492, 493, 494, 497 — assets worth roughly <1000 points). For roster-decision purposes this loss is negligible; every startable asset is present.

## 2. The value model

- **Scale: 0–9999.** Hard-capped at the top (current #1s: Josh Allen SF = 9999, Bijan Robinson 1QB = 9998). Observed floor in this snapshot: 138 (Carson Beck, 1QB rank 743). 55 of 500 assets sit below 1000.
- **Crowdsourced.** The page header states verbatim: *"KTC's dynasty fantasy football rankings crowdsource the current market value of players and picks from **26,070,016 data points** (and counting) provided by users like you."* Users answer the site's signature "Keep / Trade / Cut" three-player questions and "would-you-rather" trade comparisons; the per-record `kept` / `traded` / `cut` counters are the raw vote tallies (e.g., Josh Allen 1QB: kept 24,477 / traded 26,619 / cut 23,102; his Superflex counters are ~4x larger at 172,032 / 44,634 / 85,636 — Superflex gets far more votes and the near-universal "keep" verdict shows why he's SF #1).
- **Baseline scoring assumption:** the header labels the default view **"Superflex / .5 PPR"** — KTC values assume half-PPR scoring; the only scoring adjustments offered are the 1QB/SF toggle and TE-premium (TEP) variants. There is no separate full-PPR value set.
- **Update cadence: near-continuous.** At scrape time the page said "Values updated 4 minutes ago" and `lastProcessedTimes` showed both formats reprocessed 4 minutes prior. Values effectively refresh many times per day; a daily snapshot is more than sufficient.
- **Distribution: convex/exponential-ish with a compressed elite plateau.** 1QB value at sorted rank N (players + picks combined):

| Overall rank (by 1QB value) | 1QB value | Asset at that rank |
|---|---|---|
| 1 | 9998 | Bijan Robinson (RB) |
| 12 | 7615 | Trey McBride (TE) |
| 24 | 6593 | George Pickens (WR) |
| 48 | 5744 | Joe Burrow (QB) |
| 96 | 4479 | Michael Wilson (WR) |
| 144 | 3736 | Chris Bell (WR) |
| 192 | 3212 | Kayshon Boutte (WR) |
| 250 | 2572 | LeQuint Allen (RB) |
| 300 | 2136 | Luke Musgrave (TE) |
| 400 | 1314 | Bam Knight (RB) |
| 500 | 588 | Carson Wentz (QB) |

(Here the sorted-rank and the embedded `oneQBValues.rank` field agree at 12/24/48/96/144/192. Do NOT conflate embed position with 1QB rank at the tail: the embed's 500th entry sorted by 1QB value is Carson Beck at 138, but his `oneQBValues.rank` is 743; true 1QB rank 500 is Carson Wentz at 588.) Decay ratios per rank-doubling: #12→#24 = 0.87, #24→#48 = 0.87, #48→#96 = 0.78, #96→#192 = 0.72, #192→#384 = 0.45 — decay accelerates down the list; meanwhile the top is extremely steep (#1 9998 → #12 7615, i.e., the top ~4 assets are a class of their own: three at 9995–9998, then a cliff). Summary stats: mean 2978, median 2563. **Practical consequence for trade math: two mid-assets rarely equal one stud; KTC values are market prices, and the market prices in the roster-spot cost of quantity.**
- **Explicit tiers ship in the data** (`overallTier`, 1 = best). 1QB tier boundaries in this snapshot: tier 1 = 9995–9998 (Bijan/Chase/Gibbs), tier 2 = 9518 (JSN alone), tier 3 = 8772 (Nacua alone), tier 4 = 7396–8376, tier 5 = 6428–6951, tier 6 = 6011–6283, tier 7 ≈ 5900, tier 8 = 5382–5795, tier 9 = 5060–5279, tier 10 = 4847–4984, tier 11 = 4654–4768, then three huge catch-all tiers: 12 = 3001–4563 (122 assets), 13 = 2096–2948 (91), 14 = ≤2036 (197).

## 3. Player record schema (every field, from live data)

Top-level fields (presence out of 500 records noted where partial):

| Field | Meaning / observed values |
|---|---|
| `playerName` | Display name; for picks, the pick name (e.g., "2027 Early 1st") |
| `playerID` | KTC's stable integer ID (e.g., Josh Allen = 365). **Primary key for joins across snapshots** |
| `slug` | URL slug, `{name}-{playerID}` (player page: `keeptradecut.com/dynasty-rankings/players/{slug}`) |
| `position` | `QB` / `RB` / `WR` / `TE` / `RDP` (Rookie Draft Pick) |
| `positionID` | QB=1, RB=2, WR=3, TE=4, RDP=5 |
| `team` | NFL abbreviation (`GBP`, `LVR`, `KCC`-style 3-letter codes); `FA` for NFL free agents **and** all picks |
| `teamLongName` | e.g., "Buffalo Bills"; "Free Agent" |
| `rookie` | Boolean; 59 true in this snapshot (2026 rookie class) |
| `age` | Decimal years (e.g., 30.2); 0.0 for picks |
| `heightFeet` / `heightInches` / `weight` / `number` | Physicals + jersey number; 0 for picks |
| `seasonsExperience` | NFL seasons; **repurposed for picks** — holds a year (2026) there |
| `pickRound` / `pickNum` | Player's real NFL draft slot (0/0 for UDFAs and pick assets) |
| `draftYear` | NFL draft year (0 for picks); `college` (464 = players only); `byeWeek` (455); `birthday` (438; unix epoch **string**) |
| `isFeatured`, `isStartSitFeatured`, `isTrending`, `isDevyReturningToSchool`, `isDevyYearDecrement` | Site UI/devy flags; all devy flags false in this dataset |
| `injury` | Object: `injuryCode` (1 = none/healthy — 445 records; 2 = "Questionable" — 48; 4 = "Out" — 6; 7 = "Holdout" — 1), plus `injuryName`, `injuryArea`, `injuryReturn` when applicable |
| `mflid` | MyFantasyLeague player ID (cross-platform join key; 0 for picks). **No Sleeper ID — joining to Sleeper rosters requires name+position+team matching** |
| `oneQBValues` / `superflexValues` | The two parallel value objects — see below |

`oneQBValues` / `superflexValues` object (identical shape):

| Field | Meaning |
|---|---|
| `value` | **THE number.** Base market value, 0–9999, half-PPR, no TE premium |
| `rank` | Overall rank in that format (1QB ranks can exceed 500 here; see §1 caveat) |
| `positionalRank` | Rank within position (absent on all 36 RDP records — picks aren't positionally ranked) |
| `overallTier` / `positionalTier` | KTC's tier assignments (1 = best) |
| `overallTrend` / `positionalTrend` | **30-day rank movement** (observed −55..+81 overall). Confirmed these are rank deltas, not value deltas: the page's "Top 5 Risers (30 Days)" sidebar shows value deltas in the hundreds (e.g., +399) that don't match these small numbers |
| `overall7DayTrend` / `positional7DayTrend` | Same, 7-day window (observed −24..+31) |
| `kept` / `traded` / `cut` | Cumulative crowd vote tallies from the Keep/Trade/Cut question engine |
| `tep` / `tepp` / `teppp` | TE-premium value variants (nested objects each with own `value`, `rank`, `positionalRank`, tiers, empty `history`) — see §4 |
| `startupAdp` / `startupAvgAuctionPercentage` | Startup-draft ADP and auction share (Josh Allen: SF startupAdp 2.0) |
| `adp` / `avgAuctionPercentage` | Another ADP context (likely rookie/other drafts; 0 for picks) |
| `tradeCount` | Recent trade volume in KTC's trade database (Allen: 48 in 1QB, 133 in SF) |
| `rawLiquidity` / `stdLiquidity` | Liquidity/tradability metrics (std ~40 for stars) |
| `startSitValue`, `isOutThisWeek`, `diff` | Redraft/weekly helpers; `diff` = 0 for all records in this snapshot |
| `history` | Empty `[]` in the list embed; value history is only populated on individual player pages |
| `rookieRank`, `rookieTier`, `rookieTrend`, `rookiePositionalRank`, `rookiePositionalTier`, `rookiePositionalTrend` | Present only on the 59 `rookie: true` records — rookie-class-specific rankings |

## 4. CRITICAL — 1QB vs Superflex, and TEP

**Field selection for Chicago Dynasty (1QB, 9 starters: QB/2RB/3WR/TE/2FLEX): use `oneQBValues.value`.** Both objects always ship; no query param is needed to obtain 1QB values.

How different they are — top-12 QBs, both formats (this snapshot):

| QB | 1QB value (ovr rank) | SF value (ovr rank) | SF/1QB |
|---|---|---|---|
| Josh Allen | 7663 (#11) | 9999 (#1) | 1.30 |
| Drake Maye | 6544 (#25) | 9235 (#6) | 1.41 |
| Lamar Jackson | 6256 (#31) | 7629 (#13) | 1.22 |
| Jayden Daniels | 6181 (#38) | 7669 (#12) | 1.24 |
| Joe Burrow | 5744 (#48) | 7379 (#16) | 1.28 |
| Caleb Williams | 5707 (#49*) | 7874 (#10) | 1.38 |
| Justin Herbert | 5480 | 7067 | 1.29 |
| Jalen Hurts | 5412 | 6112 | 1.13 |
| Jaxson Dart | 5408 | 6368 | 1.18 |
| Patrick Mahomes | 5382 | 6394 | 1.19 |
| Trevor Lawrence | 5060 | 6385 | 1.26 |
| Bo Nix | 4937 | 5995 | 1.21 |

In 1QB the best QB in football is only the **#11 overall asset**, and QB5 falls to #48 overall; in SF, QBs are 4 of the top 10. Using SF values in this league would systematically overpay for QBs by ~13–41%.

**TEP variants:** inside each value object, `tep` / `tepp` / `teppp` are values recalibrated for escalating TE-premium scoring (three levels — TEP, TEP+, TEP++, i.e., increasing bonus per TE reception). Evidence: only TEs change — Brock Bowers 1QB base 8376 → tep 9267 → tepp 9999 → teppp 9999 (rank 6 → 1); Trey McBride 7615 → 8432 → 9216 → 9999; meanwhile Bijan (9998), Chase (9995), Allen (7663), and picks are identical across all four, though their *ranks* shift down as TEs leapfrog them. **Chicago Dynasty has no TE premium → use the base `value` field and ignore `tep`/`tepp`/`teppp` entirely.**

## 5. Rookie draft picks as assets

Picks are first-class assets with `position: "RDP"`, mixed into the same array and the same value scale. This snapshot has exactly **36 picks: {2026, 2027, 2028} x {Early, Mid, Late} x {1st, 2nd, 3rd, 4th}** — generic tranche picks only (no team-specific or numbered picks like "2026 Pick 1.05" in this July snapshot). Pick records have `age` 0, `team` "FA", `tradeCount` 0, and no `positionalRank`/`positionalTrend`/`positionalTier`; their `kept/traded/cut` tallies are real (picks appear in the crowd questions).

Top-5 picks by 1QB value: **2027 Early 1st = 7398 (#17 overall — worth more than every QB except Josh Allen and roughly a top-15 player), 2026 Early 1st = 6243 (#33), 2027 Mid 1st = 6118 (#41), 2028 Early 1st = 5654 (#51), 2027 Late 1st = 5562 (#59).** Full 1QB ladder highlights: 2026 Mid 1st 5279, 2026 Late 1st 4654, 2027 Early 2nd 4524, 2026 Early 2nd 4067, 2026 Mid 2nd 3630, 2026 Late 2nd 3504, 3rds ≈ 2482–3038, 4ths ≈ 1451–2163. Patterns worth encoding: next-year (2027) picks carry a premium over current-year 2026 at all 12 tranche types (optionality + a perceived stronger class), but two-years-out (2028) picks are DISCOUNTED back to roughly 2026 levels or below — 2028 beats 2026 only at the Late 1st (4768 vs 4654; e.g., 2028 Early 1st 5654 < 2026 Early 1st 6243) — so pick-valuation logic must NOT extrapolate a monotonic future-year premium. "Early vs Late" within a round is a ~15–25% spread, and picks are worth slightly MORE in 1QB than SF (e.g., 2026 Mid 1st: 5279 1QB vs 4638 SF) because rookie QBs matter less in 1QB.

## 6. Extracted dataset snapshot (2026-07-26)

Saved to **`/home/bgram/dev/dynasty-bot/data/ktc_raw.json`** — `{"_meta": {...}, "players": [500 records]}`, raw records verbatim.

- **Total assets: 500** = 464 players + 36 picks. By position: **WR 189, RB 131, TE 73, QB 71, RDP 36.** 59 rookies.

**Top 10 overall by 1QB value:**

| # | Asset | Pos | Team | Age | 1QB | SF |
|---|---|---|---|---|---|---|
| 1 | Bijan Robinson | RB | ATL | 24.5 | 9998 | 9998 |
| 2 | Ja'Marr Chase | WR | CIN | 26.4 | 9995 | 9993 |
| 3 | Jahmyr Gibbs | RB | DET | 24.4 | 9995 | 9989 |
| 4 | Jaxon Smith-Njigba | WR | SEA | 24.4 | 9518 | 9327 |
| 5 | Puka Nacua | WR | LAR | 25.2 | 8772 | 8738 |
| 6 | Brock Bowers | TE | LVR | 23.6 | 8376 | 8170 |
| 7 | Amon-Ra St. Brown | WR | DET | 26.8 | 8082 | 7930 |
| 8 | Ashton Jeanty | RB | LVR | 22.6 | 7931 | 7707 |
| 9 | Justin Jefferson | WR | MIN | 27.1 | 7762 | 7601 |
| 10 | Jeremiyah Love | RB | ARI | 21.2 | 7762 | 7550 |

**Top 5 per position by 1QB value:**

- **QB:** Josh Allen 7663, Drake Maye 6544, Lamar Jackson 6256, Jayden Daniels 6181, Joe Burrow 5744
- **RB:** Bijan Robinson 9998, Jahmyr Gibbs 9995, Ashton Jeanty 7931, Jeremiyah Love 7762, Omarion Hampton 7503
- **WR:** Ja'Marr Chase 9995, Jaxon Smith-Njigba 9518, Puka Nacua 8772, Amon-Ra St. Brown 8082, Justin Jefferson 7762
- **TE:** Brock Bowers 8376, Trey McBride 7615, Colston Loveland 6648, Tyler Warren 6460, Tucker Kraft 5586

**Value at 1QB overall ranks (the value curve):** #12 = 7615, #24 = 6593, #48 = 5744, #96 = 4479, #144 = 3736, #192 = 3212. In a 12-team league these approximate end-of-round startup prices: a "startable" asset (top ~108 = 12 teams × 9 starters) is worth ≥ ~4200; sub-2000 assets (rank ~310+) are churnable bench/waiver territory.

## 7. Daily cron scraper: practical considerations

- **Legality/politeness:** `robots.txt` is fully permissive (`User-agent: * / Allow: /`). No API terms published; KTC is a free, ad-supported community site with no official API. One page fetch per day retrieves the entire dataset — that is the whole footprint needed. Recommended: **1 request/day** (values move slowly enough day-to-day; the site itself reprocesses every few minutes but daily granularity is plenty for trade/waiver advice), a descriptive or browser UA, and generous timeout/retry with backoff (e.g., 3 attempts, 60s apart).
- **Stability:** the `playersArray` embed has been KTC's architecture for years and is what every community scraper (dynastyprocess, ktcapi wrappers) relies on; it is server-rendered so no headless browser is needed. Fragility points to guard in the parser: (a) `var playersArray` rename, (b) record shape drift (assert presence of `playerID`, `oneQBValues.value`), (c) count sanity check (expect 480–520 assets; alert outside that band), (d) possible future bot protection (Cloudflare) — if curl starts failing, fall back to Playwright (`browser_navigate` + `browser_evaluate` returning `window.playersArray` or re-scraping `document.documentElement.outerHTML`), which was loaded and available but not needed today.
- **Storage/joins:** key snapshots by `playerID` + date to build our own value history (the embedded `history` arrays are empty in the list view). Join to Sleeper via normalized name + position (+ team as tiebreaker); there is no Sleeper ID in KTC data (`mflid` is MyFantasyLeague only). Watch name punctuation ("Ja'Marr", "Amon-Ra", suffixes).
- **Fallbacks / adjacent endpoints:** individual player pages (`/dynasty-rankings/players/{slug}`) embed full value history if ever needed; KTC also has fantasy (redraft) rankings at `/fantasy-rankings` with the same embed pattern. Third-party mirrors (e.g., dynastyprocess CSV exports on GitHub) exist as an emergency fallback but lag and lack the full field set.
- **In-season note:** expect the pick asset list to change over the year (generic tranches roll forward after rookie drafts; late-season snapshots historically add next-year tranches), and `injury`/`isOutThisWeek`/trend fields become far more active in-season. Re-verify the 36-pick assumption each scrape rather than hardcoding.
