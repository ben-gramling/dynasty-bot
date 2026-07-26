# dynasty-bot knowledge base

Research docs produced 2026-07-26 from live Sleeper API pulls, a full KeepTradeCut extraction, and analysis of the `~/dev/tomato` reference repo. Every doc was adversarially fact-checked against primary sources; corrections are already applied.

## Core knowledge

| Doc | Contents |
|---|---|
| [sleeper-league.md](sleeper-league.md) | Chicago Dynasty league: full settings decode (scoring, FAAB waivers, trades, taxi/IR, playoffs), all 12 rosters, 2025 standings, pick ownership, 2025 transaction/FAAB history |
| [keeptradecut.md](keeptradecut.md) | KTC value model: extraction method, 0–9999 scale, value curve/tiers, full record schema, 1QB vs SF vs TEP variants, rookie-pick assets, scraper guidance |
| [sleeper-api.md](sleeper-api.md) | Sleeper API endpoint catalog mapped to dynasty-bot features, live-verified response shapes, offseason gotchas, rate limits |
| [reference-architecture-tomato.md](reference-architecture-tomato.md) | tomato repo architecture: AWS hosting, Terraform layout, MongoDB, Lambda crons, local dev, Playwright — copy/avoid list |

## Addenda (gap-fills)

| Doc | Contents |
|---|---|
| [ktc-sleeper-crosswalk.md](ktc-sleeper-crosswalk.md) | KTC↔Sleeper player ID join (464/464 matched), NFL team-code map, per-roster KTC 1QB totals by position, 214-player valued free-agent pool |
| [production-baselines-2025.md](production-baselines-2025.md) | 2025 actual per-player scoring in this league, positional replacement-level anchors (QB12/RB24/WR36/TE12/flex), manager efficiency |
| [rookie-draft-2026.md](rookie-draft-2026.md) | Verified 2026 rookie draft order (we pick 1.01), full KTC rookie board, concrete pick-slot pricing vs generic tranches |
| [deployment-context.md](deployment-context.md) | Live AWS/Atlas facts for deployment: ACM cert, Route53 zone, shared tomato infra, Atlas cluster state |

## Data snapshots

- `../data/ktc_raw.json` — full KTC dataset (500 assets incl. 36 picks), 2026-07-26 snapshot
- `../data/ktc_sleeper_map.json` — the KTC↔Sleeper crosswalk

## Next step

Design the team-specific scoring system (KTC value × positional need × roster strength vs league) → `scoring-system.md`.

## Key identifiers

- Sleeper user: `bengramling` / `1095425159290331136` — roster_id **4** in both seasons
- League 2026: `1312124603224555520` (pre_draft) · League 2025: `1251359014202114048` (complete)
- Format: 12-team dynasty, **1QB**, full PPR, 4-pt pass TD, QB/2RB/3WR/TE/2FLEX + 10 BN, 3 taxi, 2 IR, FAAB $50 offseason → $200 in-season from ~Aug 12 (daily processing), trade deadline wk 11, 6-team playoff wks 15–17
