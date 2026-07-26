# dynasty-bot

Fantasy-football dynasty assistant for a single Sleeper league: a daily collector
(Sleeper API sync + KeepTradeCut scrape + scoring recompute → MongoDB Atlas) and a
Next.js dashboard (Waivers / Trades / League tabs).

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
- `just plan <stack>` / `just deploy <stack>` — Terraform

## Conventions

- Python 3.12, uv workspace, hatchling per package, pytest in `[dependency-groups] dev`.
- Local secrets live in gitignored `.env` at the repo root (`MONGODB_URI`, `MONGODB_DB=dynasty-bot`) — required for anything that touches Mongo.
- Docker is NOT available locally — images build in CI only; local dev is `uv run` + `npm run dev`.
- Tests never hit live APIs — fixtures only.
- Never commit directly to `main`; work on branches.
