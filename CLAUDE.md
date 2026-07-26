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
- `just web-build` — production build of apps/web
- `just web-test` — Playwright smoke suite for apps/web
- `just plan <stack>` / `just deploy <stack>` — Terraform

## Conventions

- Python 3.12, uv workspace, hatchling per package, pytest in `[dependency-groups] dev`.
- Local secrets live in gitignored `.env` at the repo root (`MONGODB_URI`, `MONGODB_DB=dynasty-bot`) — required for anything that touches Mongo.
- Docker is NOT available locally — images build in CI only; local dev is `uv run` + `npm run dev`.
- Tests never hit live APIs — fixtures only. Exception: the web Playwright suite
  reads the live seeded `dynasty-bot` Atlas DB (it is a smoke test of real data).
- Never commit directly to `main`; work on branches.

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
