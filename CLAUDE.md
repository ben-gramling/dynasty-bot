# dynasty-bot

Fantasy-football dynasty assistant for a single Sleeper league: a daily collector
(Sleeper API sync + KeepTradeCut scrape + scoring recompute → MongoDB Atlas) and a
Next.js dashboard (Waivers / League tabs — trade-finding is CLI-only since v7.1).

Read `docs/build-plan.md` first — it locks all architecture decisions.
`docs/scoring-system.md` is THE scoring spec; its invariants and worked examples
are the test suite, pinned to the committed `data/` fixtures.

## Layout

- `libs/core/` — Python package `core`: sleeper client, ktc scraper, crosswalk, mongo layer, scoring engine
- `apps/collector/` — zip Lambda (`app.lambda_handler`), also runs locally via `just collect`
- `apps/web/` — Next.js dashboard (npm, outside the uv workspace)
- `infra/` — Terraform stacks + modules
- `data/` — committed snapshots used as test fixtures (ground truth for scoring tests)
- `docs/` — knowledge base: sleeper-api, keeptradecut, ktc-sleeper-crosswalk, scoring-system, sleeper-league

## Commands (Justfile)

- `just sync` — uv sync --all-packages
- `just collect` — run the collector locally
- `just test <pkg>` / `just test-all` — pytest
- `just web` — Next.js dev server
- `just web-build` — production build of apps/web
- `just web-test` — Playwright smoke suite for apps/web
- `just hedges [out]` — the per-counterparty hedge board as standalone HTML
- `just plan <stack>` / `just deploy <stack>` — Terraform

## Skills

- `/trade-negotiator` — interactive trade advisor backed by the scoring engine;
  scores arbitrary proposals two-sided via `scripts/score_trade.py` (standalone:
  `teams`, `list-assets`, `score --alternatives`, `pairs`, `find`, `dashboard`,
  `hedgedb build|board|offer|status`). Since v8 a session opens on the **hedge
  database**: `hedgedb build` (idempotent per content fingerprint; ~15 min on
  real changes) then `hedgedb board` writes the per-counterparty **hedge board**
  (`core/dashboard.py`, cached exact searches — seconds warm) that the skill
  publishes as an artifact. `just hedges` / `score_trade.py dashboard` is the
  legacy off-database board (one exhaustive finder run per counterparty —
  minutes). Received offers run the **pinned-offer workflow** (v8.1): verdict
  first, and an accept-worthy offer pins onto its own second artifact
  (`hedgedb offer` → `hedge-offer.html`) listing every other counterparty's
  exact hedges against it, narrowed interactively via intel/flags. Every hedge
  carries KTC trade-calculator deep links (`core/scoring/ktc_link.py`) per leg
  and for the whole spread/pair.

## League managers (real name ↔ Sleeper username)

The user refers to league-mates by real name; the data uses usernames. Map:

| Real name | Username | | Real name | Username |
|---|---|---|---|---|
| Ben Gramling (the user) | `bengramling` | | Jake Millsaps | `millj` |
| Colin | `cmgaither43` | | Joey Davis | `joeydavis299` |
| Jake Toppen | `jaketoppen` | | Vishan Lingam | `vishan` |
| Josh Ukinski | `Jukinski` | | Josh Baskin | `josbaski` |
| Theo Douglas | `trdouglas` | | Noah Moell | `NoahMoell` |
| Drew Rosenberg | `DrewR87` | | Ronak Patel | `ronakpatel32` |

First names alone can be ambiguous — "Jake" (Toppen vs Millsaps) and "Josh"
(Ukinski vs Baskin): use context or ask.

## Conventions

- Python 3.12, uv workspace, hatchling per package, pytest in `[dependency-groups] dev`.
- Local secrets live in gitignored `.env` at the repo root (`MONGODB_URI`, `MONGODB_DB=dynasty-bot`) — required for anything that touches Mongo.
- Docker is NOT available locally — images build in CI only; local dev is `uv run` + `npm run dev`.
- Tests never hit live APIs — fixtures only. Exception: the web Playwright suite
  reads the live seeded `dynasty-bot` Atlas DB (it is a smoke test of real data).
- Never commit directly to `main`; work on branches.

## Infra / deploy

- Terraform Cloud org `goldcoasttrading`, CLI-driven workspaces `dynasty-bot-shared`
  / `dynasty-bot-collector` / `dynasty-bot-web`; AWS provider pinned `5.55.0`,
  `us-east-1`, `default_tags { project = "dynasty-bot" }`. Cross-stack wiring is
  name-based data sources — the naming contract is in `infra/stacks/shared/main.tf`.
- Reuses tomato infra (`tomato-cluster`, `tomato-artifact-bucket`, the three tomato
  IAM roles — the two runtime roles are Atlas-IAM-mapped, so MONGODB-AWS auth needs
  zero new secrets). New: ECR repo `dynasty-bot`, ACM cert, ALB+Cognito, Lambda +
  daily schedule.
- Deploy order is STRICT — two manual CNAMEs at the external DNS provider gate it
  (no Route53 zone in the account). Full runbook: `docs/deploy.md`; day-2 notes:
  `infra/README.md`. Artifacts/images always upload BEFORE `terraform apply`
  (S3 ETags drive `source_code_hash`).
- `scripts/build_lambda_artifacts.sh` builds `dist/collector.zip` + `dist/layer.zip`
  for linux/x86_64 cp312 locally (no Docker needed; pymongo has C extensions, so
  never build the layer for the wrong platform).
- Local Terraform checks only: `terraform fmt -check -recursive` from `infra/`,
  and per stack `terraform init -backend=false && terraform validate`.
- The collector Lambda has no VPC config on purpose (public egress to Sleeper/KTC).

## Web local dev (apps/web)

- Needs `apps/web/.env.local` (gitignored): copy `MONGODB_URI` from the root
  `.env` and add `MONGODB_DB=dynasty-bot`. The app selects the DB by name —
  never via the URI path.
- `just web` serves on :3000. TypeScript is pinned to v6 (Next 16's compiler
  API rejects TS 7 unless `experimental.useTypeScriptCli` is enabled).
- `just web-test` runs the Playwright smoke suite on port 3100
  (`reuseExistingServer` — a pre-started `npm run dev -- -p 3100` is reused).
  Prereqs: a seeded DB (run `just collect` once) and a browser via
  `cd apps/web && npx playwright install chromium`.
- Known cosmetic build warning: "Failed to find font override values for font
  `Big Shoulders`" — no size-adjusted fallback metrics; Arial Narrow is the
  manual fallback in the font token.
