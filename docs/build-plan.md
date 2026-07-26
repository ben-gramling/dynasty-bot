# dynasty-bot Build Plan

Architecture decisions locked 2026-07-26, mirroring `~/dev/tomato` conventions (see `reference-architecture-tomato.md`, `deployment-context.md`). Build proceeds in three phases: **A** core library + collector, **B** web app, **C** infra/deploy.

## Repo layout (tomato-style uv monorepo)

```
dynasty-bot/
├── apps/
│   ├── collector/      # zip Lambda: Sleeper sync + KTC scrape + scoring recompute → Mongo (daily cron + on-demand)
│   └── web/            # Next.js dashboard (npm, OUTSIDE the uv workspace) — Waivers / Trades / League tabs
├── libs/
│   └── core/           # Python package `core`: sleeper client, ktc scraper, crosswalk, mongo layer, scoring engine
├── infra/
│   ├── stacks/         # shared, collector, web  (Terraform Cloud backend, org goldcoasttrading, ws dynasty-bot-<stack>)
│   └── modules/        # lambda_function (tomato pattern: S3 zip + etag source_code_hash + EventBridge rule)
├── data/               # committed snapshots used as test fixtures (ktc_raw.json, ktc_sleeper_map.json, sleeper fixtures)
├── docs/               # knowledge base + this plan + scoring-system.md (the spec)
├── scripts/            # ad-hoc operational scripts
├── Justfile            # sync / collect / test <pkg> / test-all / web / plan <stack> / deploy <stack>
├── pyproject.toml      # uv workspace root (members: libs/*, apps/collector)
└── CLAUDE.md           # onboarding doc
```

## Decisions

| Area | Decision |
|---|---|
| Python | 3.12, uv workspace, hatchling per package, pytest in `[dependency-groups] dev` |
| Collector | ONE zip Lambda `dynasty-bot-collector` (python3.12, `app.lambda_handler`, 600s, deps in a Lambda layer), EventBridge `cron(0 10 * * ? *)` daily (10:00 UTC); on-demand via web "Refresh" (lambda:InvokeFunction) and locally `just collect` |
| Collector job | Sleeper pulls (league, rosters, users, traded_picks, drafts+picks, transactions, players-dump 1×/day, trending, state) → KTC scrape (playersArray, 1 request, browser UA) → crosswalk (auto-join + the 5 manual overrides from `ktc-sleeper-crosswalk.md`) → scoring engine (full recompute) → Mongo upserts + run log |
| Scoring engine | `libs/core/core/scoring/` — pure functions over a `Snapshot` input; implements `scoring-system.md` exactly; §13 invariants + §11 worked examples are the pytest suite, pinned to committed `data/` fixtures with EXACT expected numbers |
| Mongo | Atlas cluster `tributary-dev.ygqeljj.mongodb.net`, database **`dynasty-bot`** (new). AWS: MONGODB-AWS IAM auth reusing tomato roles (`tomato-lambda-exec-role`, `tomato-ecs-task-role` — both already Atlas-mapped, zero new secrets). Local: user/pass URI in gitignored `.env` (copy from tomato's env files) |
| Collections (kebab-case, one accessor fn each in `core/collections.py`) | `league`, `rosters`, `users`, `picks`, `transactions`, `players` (Sleeper dump subset), `ktc-latest`, `ktc-history` (daily per-player values — powers the DIP flag), `crosswalk`, `waiver-board`, `trade-recs`, `league-table`, `runs` |
| Web | Next.js App Router `output:"standalone"`, server components query Mongo directly (no REST layer), Tailwind, Recharts if charts needed; tabs: Waivers, Trades, League; header shows last-collector-run + Refresh button (server action → lambda invoke in AWS, local subprocess fallback) |
| Web hosting | ECS Fargate 512/1024 ×1 on `tomato-cluster` + new ALB (443-only) + Cognito (single user bgramling18@gmail.com) + NEW ACM cert; hostname `dynasty.sarikayakomzin.com` (DNS + cert-validation CNAMEs manual at external provider) |
| ECR | New repo `dynasty-bot`, tags `<app>-<sha>` / `<app>-latest`, per-prefix lifecycle keep-10 |
| CI | GitHub Actions: reusable deploy-ecs/deploy-lambda/deploy-infra, per-app path-filtered workflows, artifact-before-apply ordering; TFC remote runs |
| Testing | pytest per package (`just test-all`); scoring fixtures exact-match; Playwright: `@playwright/test` smoke suite in `apps/web` + Playwright-MCP interactive verification of the local site |
| Improvements over tomato (from its avoid-list) | `default_tags {project="dynasty-bot"}`; no hardcoded webhooks/URIs in .tf; scoped IAM where we create roles; secrets under `dynastybot/` prefix if any needed (likely none — IAM auth covers Mongo) |

## Phase status

- **A — core + collector**: scaffold → (data pipeline ∥ scoring engine) → integrate, seed real `dynasty-bot` DB, full test pass
- **B — web app**: three tabs + local dev + Playwright verification against the seeded DB
- **C — infra/CI/deploy**: build all Terraform + workflows; `terraform apply` and DNS/cert steps require user go-ahead (manual CNAMEs at external DNS)

## Local dev quirks

- Docker is NOT available in this WSL distro — images build in CI only; local dev = `npm run dev` + `uv run`.
- Never commit `.env` / `.env.local`; Mongo local URI comes from tomato's gitignored env files.
- The committed `data/` fixtures are the scoring-test ground truth — regenerating them changes expected numbers and must be deliberate.
