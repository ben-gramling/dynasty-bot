# Reference Architecture: tomato

Reference analysis of `/home/bgram/dev/tomato` — the repo dynasty-bot will imitate architecturally (uv monorepo, Terraform-on-AWS, MongoDB Atlas, scheduled Lambdas/ECS tasks, Next.js dashboard, GitHub Actions CI/CD). All claims below cite exact file paths in that repo.

Tomato itself is a trading ecosystem for Kalshi Rotten Tomatoes (KXRT) markets: scrapers collect Rotten Tomatoes review data, a fair-value service computes market fair values, and a Next.js dashboard visualizes them. The domain logic is irrelevant to dynasty-bot; the delivery architecture is the template.

---

## 1. Repo layout and conventions

Top-level layout (documented in `/home/bgram/dev/tomato/CLAUDE.md`, verified on disk):

```
tomato/
├── apps/                  Deployable applications (one dir each)
│   ├── scrapers/          4 small scrapers: kalshi-events, movies, reviews (zip Lambdas), reviews-post (ECS task)
│   ├── orchestrator/      ECS Fargate scheduled task + on-demand container-image Lambda
│   ├── fv-service/        Long-running ECS Fargate service
│   ├── dashboard/         Next.js UI (ECS Fargate + ALB + Cognito) — npm project, NOT in the uv workspace
│   ├── trader/            (tomato-specific) trading app
│   └── orderbook-ws/      (tomato-specific)
├── libs/                  Shared Python packages, all uv workspace members
│   ├── shared/            AWS/Mongo/Discord/logging utilities
│   ├── rt-tools/          domain scraping lib
│   ├── fv-engine/         model lib
│   └── kalshi-client/     API client lib
├── infra/
│   ├── stacks/            One Terraform root module ("stack") per app + shared
│   └── modules/           Reusable modules: lambda_function, lambda_layer
├── .github/workflows/     CI/CD (reusable + per-app workflows)
├── docs/                  mongo.md, domain docs, investigations/
├── scripts/               One-off operational scripts (ad-hoc, never deployed)
├── Justfile               Local dev shortcuts
├── pyproject.toml         uv workspace root
└── uv.lock                Single lock for the whole workspace
```

### Package management (uv workspace)

`/home/bgram/dev/tomato/pyproject.toml` is a minimal workspace root:

```toml
[project]
name = "tomato"
version = "0.1.0"
requires-python = ">=3.12"

[tool.uv.workspace]
members = ["libs/*", "apps/scrapers/*", "apps/orchestrator", "apps/fv-service", "apps/trader"]
```

- Each lib/app has its own `pyproject.toml` with hatchling as build backend; workspace deps are declared as `shared = { workspace = true }` under `[tool.uv.sources]` (e.g. `/home/bgram/dev/tomato/apps/fv-service/pyproject.toml`, `/home/bgram/dev/tomato/apps/scrapers/movies/pyproject.toml`).
- Dev deps go in `[dependency-groups] dev = [...]` (pytest, pytest-asyncio).
- `just sync` → `uv sync --all-packages`. One `uv.lock` for everything.
- The Next.js dashboard is deliberately **outside** the uv workspace — plain npm with its own `package.json`/`package-lock.json`.
- `.envrc` (direnv) just puts `.venv/bin` on PATH.

### Justfile targets (`/home/bgram/dev/tomato/Justfile`)

| Recipe | Command |
|---|---|
| `just scraper <name>` | `cd apps/scrapers/{{name}} && uv run python -m app` |
| `just orchestrator *args` | `uv run python apps/orchestrator/scripts/run_local.py {{args}}` |
| `just test <pkg>` | `cd {{pkg}} && uv run pytest` |
| `just test-all` | pytest over `libs/rt-tools/tests/` and `apps/orchestrator/tests/` |
| `just build <app>` | `docker build -t tomato-{{app}} apps/{{app}}` |
| `just plan <stack>` / `just deploy <stack>` | `cd infra/stacks/{{stack}} && terraform plan` / `terraform apply` |
| `just sync` | `uv sync --all-packages` |

The dashboard is not in `just` — `cd apps/dashboard && npm run dev`.

### Other conventions

- `CLAUDE.md` at the root is the authoritative onboarding doc; `apps/dashboard/CLAUDE.md` is just `@AGENTS.md`, and `apps/dashboard/AGENTS.md` warns that the installed Next.js (16.2.2) has breaking changes vs. training data — "read `node_modules/next/dist/docs/` before writing code".
- Branching: never commit directly to `main`; every change lands via a PR; larger features use git worktrees under `.worktrees/` (gitignored).
- `.gitignore` covers `.env`, `*.pem`, `*.tfvars`, `.terraform/`, `.mcp.json`, `.claude/`, `.playwright-mcp/`, `.worktrees/`.
- `.terraformignore` at repo root excludes `.git/`, `node_modules/`, `.next/`, `.venv/`, `docs/`, etc. from Terraform Cloud uploads.
- MCP servers configured in `.mcp.json` (gitignored): `cloudwatch` (awslabs.cloudwatch-mcp-server via uvx) and `terraform` (hashicorp/terraform-mcp-server Docker image with a TFE token). MongoDB access from Claude Code uses the `mongodb-atlas` MCP.

---

## 2. The website subproject (`apps/dashboard`)

### Framework

- **Next.js 16.2.2 (App Router) + React 19.2.4**, TypeScript, Tailwind CSS 4 (via `@tailwindcss/postcss`), **Recharts 3.8.1** for charts, **`mongodb` driver 7.1.1** + `@aws-sdk/credential-providers` (`/home/bgram/dev/tomato/apps/dashboard/package.json`).
- It is a **full-stack Next.js server app** — server components query MongoDB directly (`src/lib/queries.ts` imports the Mongo client; no separate REST backend, no API Gateway).
- `next.config.ts`: `output: "standalone"` and `serverExternalPackages: ["@aws-sdk/credential-providers"]` (the AWS credential provider must be traced into the standalone build because the Mongo driver loads it dynamically for MONGODB-AWS auth — see comment in `src/lib/mongodb.ts`).
- Pages: `src/app/page.tsx` (home), `src/app/movie/[emsId]/page.tsx`, `src/app/movie/[emsId]/market/[ticker]/page.tsx`; components in `src/components/` (fv-table, reviews-table, charts, sidebar, time-range-selector).
- Mongo connection: `src/lib/mongodb.ts` — lazy singleton `MongoClient` promise; in `development` it is cached on `global` to survive hot reload.

### Build & container

`/home/bgram/dev/tomato/apps/dashboard/Dockerfile` — two-stage `node:20-slim` build: `npm ci` → `npm run build`, then the runner copies `.next/standalone`, `.next/static`, `public/` and runs `node server.js` on port 3000. Docker build context is the **repo root** (CI builds with `-f apps/dashboard/Dockerfile .`).

### Serving on AWS — NOT S3/CloudFront, NOT API Gateway

The dashboard is an **ECS Fargate service behind an internet-facing ALB with Cognito auth** (`/home/bgram/dev/tomato/infra/stacks/dashboard/main.tf`):

- `aws_ecs_service.dashboard`: FARGATE, `desired_count = 1`, in the **default VPC** subnets with `assign_public_ip = true` (no NAT, no private subnets).
- `aws_ecs_task_definition.dashboard`: 512 CPU / 1024 MB, X86_64, image `${var.ecr_repo_url}:${var.image_tag}` (default `327989636102.dkr.ecr.us-east-1.amazonaws.com/tomato` : `dashboard-latest`), env `MONGODB_URI` (MONGODB-AWS URI) and `NODE_ENV=production`, awslogs to `/ecs/dashboard` (30-day retention).
- `aws_lb.dashboard` (`dashboard-alb`) + `aws_lb_target_group.dashboard` (`dashboard-tg`, port 3000, `target_type = "ip"`, health check on `/`).
- `aws_lb_listener.https`: port 443 only, `ELBSecurityPolicy-TLS13-1-2-2021-06`, `certificate_arn = var.certificate_arn`. Two ordered `default_action` blocks: first `authenticate-cognito`, then `forward` — every request must pass Cognito login.
- Security groups: `dashboard-alb-sg` allows 443 from 0.0.0.0/0; `dashboard-sg` allows 3000 only from the ALB SG. No HTTP:80 listener at all.
- **Cognito**: `aws_cognito_user_pool` `dashboard-user-pool`, `aws_cognito_user_pool_client` `dashboard-alb-client` (code flow, `openid` scope, generated secret, callback `https://tomato.sarikayakomzin.com/oauth2/idpresponse`), hosted domain prefix `tomato-dashboard`, and a single `aws_cognito_user.owner` created from `var.cognito_user_email`. This is the entire auth system — one user, provisioned by Terraform.

### Domain / TLS

- Hostname `tomato.sarikayakomzin.com` (root CLAUDE.md §apps/dashboard).
- TLS: an **ACM certificate ARN is passed in as a Terraform variable** (`variable "certificate_arn"`, no default, in `infra/stacks/dashboard/variables.tf`) — the cert is provisioned outside this repo, presumably manually, and the ARN is set as a TFC workspace variable.
- **There are no Route53 or ACM resources anywhere in `infra/`** (verified by grep). DNS for `tomato.sarikayakomzin.com` → ALB is managed outside Terraform.

---

## 3. Terraform

### Structure

- `infra/stacks/` — six independent root modules: `shared`, `scrapers`, `orchestrator`, `fv-service`, `dashboard`, `trader`. Each stack has `main.tf` (+ optional `variables.tf`, `outputs.tf`; shared also has `iam.tf`, `secrets.tf`).
- `infra/modules/` — two reusable modules: `lambda_function` (zip Lambda + EventBridge cron rule + invoke permission) and `lambda_layer`.

### State backend: Terraform Cloud

Every stack's `terraform {}` block uses the `cloud` backend, org **`goldcoasttrading`**, one workspace per stack named `tomato-<stack>` (e.g. `/home/bgram/dev/tomato/infra/stacks/shared/main.tf` → workspace `tomato-shared`; likewise `tomato-scrapers`, `tomato-orchestrator`, `tomato-fv-service`, `tomato-dashboard`, `tomato-trader`).

### Providers / versions

Identical in every stack: `hashicorp/aws` **pinned exactly to `5.55.0`**, `required_version = ">= 1.1.0"`, `provider "aws" { region = "us-east-1" }`. AWS account `327989636102`.

### Cross-stack wiring — name-based data sources, not remote state

The `shared` stack owns cluster/roles/bucket/ECR/secrets; app stacks look them up **by name with data sources**, e.g. in `infra/stacks/dashboard/main.tf`:

```hcl
data "aws_ecs_cluster" "tomato" { cluster_name = "tomato-cluster" }
data "aws_iam_role" "ecs_execution" { name = "tomato-ecs-execution-role" }
data "aws_secretsmanager_secret" "anthropic" { name = "goldcoastgroup/anthropic-api-key" }
data "aws_vpc" "default" { default = true }
```

`shared` also defines `outputs.tf` (role ARNs, subnet ids, bucket, secret ARNs) but the other stacks do not consume them via `terraform_remote_state` — everything is name-convention lookups. This keeps stacks decoupled and independently applyable, at the cost of implicit naming contracts.

### Shared stack contents (`infra/stacks/shared/`)

- `aws_ecs_cluster` `tomato-cluster` with `containerInsights = "enhanced"` (plus an `import {}` block — pre-existing resources were adopted with Terraform 1.5+ import blocks).
- Default-VPC + subnet data sources (no custom networking whatsoever).
- `aws_s3_bucket` `tomato-artifact-bucket` (Lambda zips + layer zip).
- One `aws_ecr_repository` `tomato` for **all** app images, tags namespaced `<app>-<sha>` / `<app>-latest`, with a **per-app-prefix lifecycle policy** (keep last 10 per prefix). A long code comment explains why: a previous repo-wide `imageCountMoreThan: 25` rule let a fast-moving app evict other apps' `-latest` tags, silently breaking scheduled runs.
- `iam.tf`: three shared roles — `tomato-lambda-exec-role`, `tomato-ecs-execution-role`, `tomato-ecs-task-role`. Policies are broad (`secretsmanager:GetSecretValue` and S3 on `Resource: "*"`; SQS SendMessage on `arn:aws:sqs:*:*:*`).

### Environment separation

**There is none.** Single AWS account, single region, one production environment, no dev/staging stacks, no `tfvars` per env. The only env-like switch is app-level (`DEMO=true` selects the Kalshi demo API).

### Naming / tagging

- Names are flat and convention-based: `tomato-*` for shared/Lambda resources (`tomato-kalshi-scraper`, `tomato-lambda-exec-role`), app-name-first for app resources (`dashboard-alb`, `dashboard-tg`, `orchestrator-sg`, `fv-service-sg`, `reviews-post-schedule`).
- Log groups: `/ecs/<app>` and `/aws/lambda/<name>`, always `retention_in_days = 30`.
- **No `tags` on any resource and no `default_tags`** — there is no tagging convention.

### Secrets handling

- **AWS Secrets Manager**, all under prefix `goldcoastgroup/` (`infra/stacks/shared/secrets.tf`): `goldcoastgroup/kalshi-prod-private-key`, `goldcoastgroup/kalshi-demo-private-key`, `goldcoastgroup/anthropic-api-key`. Secret **values** enter Terraform as variables (`var.kalshi_prod_key_content`, etc., set in the TFC workspace) and are written via `aws_secretsmanager_secret_version`.
- Injection into workloads, two patterns:
  1. ECS `secrets` block: `{ name = "ANTHROPIC_API_KEY", valueFrom = data.aws_secretsmanager_secret.anthropic.arn }` (orchestrator, reviews-post task defs) — the value never touches TF config.
  2. Lambda: pass the **ARN** as env (`ANTHROPIC_SECRET_ARN`, `KALSHI_PROD_SECRET_ARN`) and fetch at runtime via `shared.aws.get_secret` (`libs/shared/shared/aws.py`, a 10-line boto3 `get_secret_value` wrapper with client singleton).
- No SSM Parameter Store use.
- Anti-pattern present: the Discord webhook URL is **hardcoded in plain text** in several `.tf` files (`infra/modules/lambda_function/variables.tf` default `lambda_env`, `infra/stacks/orchestrator/main.tf`, `infra/stacks/scrapers/main.tf`) and the state-inspecting MCP config `.mcp.json` contains a TFE token (gitignored, but still plaintext on disk).

### The `lambda_function` module (`infra/modules/lambda_function/`)

- `main.tf`: `aws_lambda_function` from S3 (`s3_bucket` + `s3_key`), `timeout = 600`, default `handler = "app.lambda_handler"`, default `runtime = "python3.12"`, layers list, and crucially `source_code_hash = data.aws_s3_object.lambda_zip.etag` — Terraform redeploys the function **only when the S3 zip's ETag changes**.
- `cloudwatch.tf`: `aws_cloudwatch_event_rule` named `invoke-<function_name>` with `schedule_expression = var.cron_schedule`, an `aws_cloudwatch_event_target`, and `aws_lambda_permission` for `events.amazonaws.com`. So zip Lambdas are scheduled with classic **EventBridge rules**.
- `variables.tf` carries a `lambda_env` map default containing `MONGODB_URI`, `ENVIRONMENT=aws`, `DEMO`, key IDs, and webhook — merged with per-function additions.
- `lambda_layer` module: `aws_lambda_layer_version` from S3 with the same `source_code_hash = etag` trick, so a new layer version is published only when the zip content changes.

---

## 4. MongoDB

- **MongoDB Atlas**, cluster host `tributary-dev.ygqeljj.mongodb.net` (visible in every task definition and in `apps/dashboard/.env.local`).
- **Auth, two modes** (root CLAUDE.md §Data layer):
  - In AWS (ECS + Lambda): **`MONGODB-AWS` IAM auth** — connection string `mongodb+srv://tributary-dev.ygqeljj.mongodb.net/arbriver?authSource=$external&authMechanism=MONGODB-AWS`, injected as a plain `MONGODB_URI` env var in every ECS task definition and the Lambda `lambda_env` default. The task/exec IAM role authenticates; **no password exists in AWS config**. The `/arbriver` path segment is a quirk of how the Atlas AWS-auth user was set up — that database is explicitly *not* used; every app selects its DB by name.
  - Locally: username+password SRV URI in gitignored `.env` (Python apps, loaded via `python-dotenv`'s `load_dotenv()`) and `apps/dashboard/.env.local` (Next.js).
- **Databases**: `kxrt` (live) and `kxrt-training` (historical/training). Documented in `/home/bgram/dev/tomato/docs/mongo.md`.
- **Collection naming**: kebab-case collection names (`fv-cache`, `fv-history`, `bad-events`, `reviews-all`, `movies-all`, `orderbook-active`), singular-concept plural nouns.
- **Access libraries**:
  - Python: **pymongo** (`pymongo[aws]` in `libs/shared/pyproject.toml` for the AWS auth extra; apps also list `pymongo-auth-aws`). `libs/shared/shared/db.py` provides a `MongoClient` singleton (`serverSelectionTimeoutMS=30000` — deliberately kept at 30s so an Atlas primary election doesn't kill non-restarting scheduled tasks; `connectTimeoutMS=5000`, `socketTimeoutMS=30000`, `maxIdleTimeMS=60000`), `get_db(db_name="kxrt")`, and `set_db()` for test injection.
  - `libs/shared/shared/collections.py` defines **one accessor function per collection** (`events()`, `movies()`, `reviews()`, `fv_history()`, …) so collection names live in exactly one place.
  - TypeScript (dashboard): official **`mongodb`** node driver + `@aws-sdk/credential-providers`, singleton promise in `src/lib/mongodb.ts`, typed document interfaces + query functions in `src/lib/queries.ts` (`getDb(name = "kxrt")`).
- Interactive access from Claude Code goes through the `mongodb-atlas` MCP server rather than ad-hoc scripts.

---

## 5. Scheduled / cron jobs

Three distinct patterns, all in production:

### a) Zip Lambdas on EventBridge rules (small, < 10 min jobs)

`infra/stacks/scrapers/main.tf` instantiates the `lambda_function` module three times:

| Function | Schedule | Purpose |
|---|---|---|
| `tomato-kalshi-scraper` | `cron(0/15 * * * ? *)` (15 min) | list Kalshi events |
| `tomato-review-scraper` | `cron(0/1 * * * ? *)` (every minute) | scrape RT reviews |
| `movies-all-scraper` | `cron(0 0 * * ? *)` (daily 00:00 UTC) | discover upcoming movies |

- Packaging: CI zips only the app's `*.py` files to `s3://tomato-artifact-bucket/functions/<name>.zip`; all third-party + workspace-lib deps live in one shared **Lambda layer** (`layer/layer.zip`, built by `uv build` each lib wheel then `uv pip install --target layer/python`). See `.github/workflows/deploy-lambda.yml`.
- Code layout: each scraper is a flat dir with `app.py` exposing `lambda_handler(event, context)` plus `if __name__ == "__main__": lambda_handler(None, None)` so `just scraper <name>` (`python -m app`) runs it locally (`apps/scrapers/movies/app.py`).
- Lambda timeout 600 s.

### b) ECS Fargate scheduled tasks via EventBridge Scheduler (jobs > 15 min)

Used when "a full pass exceeds Lambda's 15-min ceiling" (comment in `infra/stacks/scrapers/main.tf`): `reviews-post` (daily `cron(0 12 * * ? *)`) and the `orchestrator` (hourly `cron(0 * * * ? *)`, 4096 CPU / 8192 MB, in `infra/stacks/orchestrator/main.tf`). Pattern per job:

- `aws_ecs_task_definition` (no service — it's run-to-completion),
- a dedicated `aws_iam_role` assumable by `scheduler.amazonaws.com` with `ecs:RunTask` (conditioned on the cluster ARN, targeting `task_definition.arn_without_revision:*`) + `iam:PassRole` for the exec/task roles,
- `aws_scheduler_schedule` with `schedule_expression_timezone = "UTC"`, `flexible_time_window { mode = "OFF" }`, and `ecs_parameters` carrying launch type + network config (`assign_public_ip = true`, egress-only SG).

### c) On-demand container-image Lambda

`generate-scraper` (`infra/stacks/orchestrator/main.tf`): `package_type = "Image"`, `image_uri = <ecr>:generate-scraper-latest`, timeout 900 s, 1024 MB, no schedule — invoked manually with a JSON payload (`{"publication_id": 337, "model": "opus"}` per CLAUDE.md). Its Dockerfile (`apps/orchestrator/Dockerfile.lambda`) is a plain `python:3.12-slim` image with `awslambdaric` as entrypoint (not the AWS base image).

**Container-image Lambda gotcha** (documented in `.github/workflows/orchestrator.yml`): Lambda resolves the `-latest` tag to a digest at update time and caches it; Terraform sees no diff on the tag string. CI therefore runs an explicit `aws lambda update-function-code --image-uri ...-latest` step after pushing (guarded by `aws lambda get-function` for first provisioning).

**On-demand triggering** of scheduled things: zip Lambdas can be invoked via `aws lambda invoke` / console; ECS scheduled tasks via `aws ecs run-task`; and everything has a local entrypoint (`just scraper`, `just orchestrator` → `apps/orchestrator/scripts/run_local.py` with `--pub/--limit/--workers`).

### Alarms

One example: `aws_cloudwatch_metric_alarm` `tomato-kalshi-scraper-errors` (Lambda `Errors` Sum ≥ 2 in 1800 s, `treat_missing_data = "notBreaching"`) → `aws_sns_topic` `tomato-scrapers-alerts` (`infra/stacks/scrapers/main.tf`). Otherwise alerting is app-level Discord webhooks (`libs/shared/shared/discord.py`, env `DISCORD_WEBHOOK_URL`).

---

## 6. Local development

- `just sync` once after checkout (uv workspace).
- Python apps: `just scraper movies|reviews|kalshi-events`, `just orchestrator --pub 337 --limit 5`; every entrypoint calls `load_dotenv()` so gitignored `.env` supplies `MONGODB_URI` (user/pass Atlas URI), `ANTHROPIC_API_KEY`, `DISCORD_WEBHOOK_URL`, `ENVIRONMENT`, feature flags, Kalshi key IDs/keyfile paths, Langfuse keys.
- Dashboard: `cd apps/dashboard && npm run dev` → `next dev` at `http://localhost:3000`; `apps/dashboard/.env.local` holds a plain `MONGODB_URI=mongodb+srv://admin:<password>@tributary-dev.ygqeljj.mongodb.net/`.
- Tests: `just test <pkg>` / `just test-all` (pytest per package: `libs/shared/tests/`, `libs/rt-tools/tests/`, `apps/orchestrator/tests/`, `apps/fv-service/tests/`, `apps/trader/tests_e2e/`).
- **Playwright**: there is **no Playwright test suite** in tomato (no `playwright.config.*`, no `@playwright/test` dependency anywhere). Playwright is used through the **Claude Code Playwright MCP plugin** (`mcp__plugin_playwright_playwright__browser_*` tools) to drive and visually verify the locally running dashboard interactively; the artifacts of these sessions live in `/home/bgram/dev/tomato/.playwright-mcp/` (page snapshots `.yml`, screenshots `.png`, console logs; gitignored). So "Playwright testing" in tomato = agent-driven browser verification, not CI tests. The only automated E2E is Python: `.github/workflows/trader-e2e.yml` runs `uv run --package trader pytest apps/trader/tests_e2e/scenario.py -m e2e` on PRs/pushes, with a manual changed-path filter to short-circuit unrelated changes, against a dedicated `kxrt-integration` Mongo DB and a Dockerized app under test.

---

## 7. Deploy workflow (GitHub Actions + Terraform Cloud)

All in `/home/bgram/dev/tomato/.github/workflows/`.

### Three reusable (`workflow_call`) workflows

1. **`deploy-ecs.yml`** — checkout → ECR login → `docker build` with **repo-root context** (`-f <app_path>/Dockerfile .`, so images can `COPY libs/`) tagged `<app>-<sha>` and `<app>-latest` → push both → `aws ecs update-service --force-new-deployment`.
2. **`deploy-lambda.yml`** — zips `*.py` from the app dir to `s3://tomato-artifact-bucket/functions/<name>.zip`; if `build_layer: true`, builds the shared layer (uv-built wheels of `shared`, `kalshi-client`, `rt-tools` installed into `layer/python`, zipped) to `s3://.../layer/layer.zip`. **Deliberately does not touch the Lambda function** — the follow-up Terraform apply sees the new S3 ETag via `source_code_hash` and updates the function.
3. **`deploy-infra.yml`** — `terraform init` + `plan` (always), then an `apply -auto-approve` job gated on `main` (or `auto_apply` input) and bound to the GitHub `environment: production`. Auth via `hashicorp/setup-terraform@v3` with `cli_config_credentials_token: ${{ secrets.TF_API_TOKEN }}` (Terraform Cloud remote runs).

### Per-app workflows

Trigger on `push: main` with **path filters** so only the affected app redeploys; each ends with the matching `deploy-infra(<stack>)`:

- `dashboard.yml`: paths `apps/dashboard/**`, `infra/stacks/dashboard/**` → `deploy-ecs(dashboard)` → `deploy-infra(dashboard)`.
- `fv-service.yml`: app + `libs/shared/**` + `libs/fv-engine/**` paths → `deploy-ecs` → `deploy-infra`.
- `scrapers.yml`: three `deploy-lambda` calls (only the first has `build_layer: true`; the others `needs:` it so the layer zip exists in S3 before Terraform reads its ETag) + an inline Docker build for `reviews-post` → `deploy-infra(scrapers)` `needs:` all four.
- `orchestrator.yml`: inline builds/pushes of both images + the `update-function-code` digest-refresh step → `deploy-infra(orchestrator)`.
- `shared-infra.yml`: infra-only.

Ordering invariant stated in comments: **artifacts must land in S3/ECR before `terraform apply`**, because Terraform reads ETags/digests at plan time.

### Required GitHub secrets

`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` (static keys, not OIDC), `TF_API_TOKEN`; the e2e workflow adds `MONGODB_URI_INTEGRATION` and Kalshi demo keys.

---

## 8. Copy this / avoid this for dynasty-bot

### Copy verbatim (proven, low-friction)

1. **Monorepo shape**: `apps/` + `libs/` + `infra/stacks|modules` + `scripts/` + root `Justfile` + uv workspace with `{ workspace = true }` sources and a single `uv.lock`; hatchling per package; npm web app outside the uv workspace.
2. **Terraform Cloud backend, one workspace per stack** (`dynastybot-shared`, `dynastybot-<app>`), pinned AWS provider, `us-east-1`, a `shared` stack owning cluster/ECR/bucket/roles/secrets and app stacks reading them via name-based data sources.
3. **`source_code_hash = data.aws_s3_object.<x>.etag`** pattern in `lambda_function`/`lambda_layer` modules — CI uploads artifact, Terraform deploys it; simple and race-free when CI orders upload → apply.
4. **Scheduling split**: zip Lambda + EventBridge rule for < 10-min jobs (e.g. nightly KTC-value scrape, Sleeper roster sync); EventBridge Scheduler → `ecs:RunTask` Fargate task (with the dedicated scheduler role + `arn_without_revision:*` + `iam:PassRole`) for long jobs; on-demand container Lambda for manual heavy operations. Keep the `-latest`-digest refresh step if using image Lambdas.
5. **MongoDB Atlas with `MONGODB-AWS` IAM auth in AWS** (URI has no credentials; the IAM role is the credential) and user/pass `.env` locally; pymongo singleton with tuned timeouts (`libs/shared/shared/db.py`); one accessor function per collection (`shared/collections.py`); Node `mongodb` driver + `@aws-sdk/credential-providers` + `serverExternalPackages` for the Next.js side.
6. **Dashboard serving stack**: Next.js `output: "standalone"`, two-stage node:20-slim Dockerfile, repo-root build context, ECS Fargate `desired_count 1` (512/1024) + ALB (443-only, TLS 1.3 policy) + `authenticate-cognito` default action + a Terraform-provisioned single Cognito user — the cheapest way to get an authenticated personal web app. For dynasty-bot (one user: bgramling18@gmail.com) this maps 1:1.
7. **CI layout**: reusable `deploy-ecs` / `deploy-lambda` / `deploy-infra` workflows; per-app workflows on `push: main` with path filters; plan-always/apply-on-main gated by a GitHub environment; artifact-before-apply ordering.
8. **Conventions**: single ECR repo with `<app>-<sha>` / `<app>-latest` tags **and per-prefix lifecycle rules** (the repo-wide-rule outage is documented in `infra/stacks/shared/main.tf` comments — don't relearn it); `/ecs/<app>` + `/aws/lambda/<app>` log groups at 30-day retention; a rich root `CLAUDE.md`; Secrets Manager under one project prefix with ECS `valueFrom` or `*_SECRET_ARN` + a `get_secret` helper; `set_db()` test-injection hook; Discord webhook alerting helper; Playwright-MCP interactive verification of the local dashboard.
9. **Ops ergonomics**: every scheduled job runnable locally (`lambda_handler(None, None)` under `__main__`, `run_local.py` with flags) and on demand in AWS; a small CloudWatch alarm → SNS on critical Lambda errors.

### Tomato-specific or deliberately avoid

1. **Domain logic**: everything about KXRT/Kalshi/RT — scrapers' content, fv-engine, trader, orderbook-ws, `docs/rotten-tomatoes-markets.md`, the `kxrt*` databases. Dynasty-bot replaces this with Sleeper league/roster sync + KTC value scraping + a scoring/recommendation engine.
2. **Hardcoded Discord webhook URL and Mongo URIs inline in `.tf` files** — put them in variables/Secrets Manager instead. Likewise the plaintext admin password in `apps/dashboard/.env.local` and the TFE token in `.mcp.json` (gitignored but risky).
3. **IAM wildcards** (`secretsmanager:GetSecretValue` and S3 on `Resource: "*"` in `infra/stacks/shared/iam.tf`) — scope to the project's ARNs.
4. **No environment separation / no tags** — acceptable for a personal single-env project, but at minimum add `default_tags` (project = dynasty-bot) so costs are attributable.
5. **Static AWS access keys in GitHub secrets** — prefer OIDC role assumption if setting up fresh.
6. **The `arbriver` default-DB quirk** in the Mongo URI — an artifact of tomato's Atlas AWS-auth setup; if reusing the same cluster the same caveat applies (always select the DB explicitly), otherwise name the auth path after the real DB.
7. **Manual, out-of-band ACM cert + DNS** — tomato passes `certificate_arn` as an unset-default TFC variable and manages DNS outside Terraform. Workable, but for dynasty-bot consider bringing the `aws_acm_certificate` + Route53/DNS records into the stack (or at least document where they live) since this was left implicit in tomato.
8. **The shared Lambda layer coupling** (`build_layer: true` on exactly one job, others `needs:` it) works but is fragile ordering; with only 1-2 Lambdas dynasty-bot could bundle deps per-function or reuse the pattern knowingly.
9. **Two orchestrator entrypoints in one package with two Dockerfiles** — only copy if dynasty-bot actually needs an agentic pipeline plus an on-demand generator.

### Quantities worth remembering when sizing dynasty-bot

- Dashboard: 512 CPU / 1024 MB Fargate, 1 task. fv-service: 1024/2048. Heavy hourly batch: 4096/8192. Lambda: default 600 s timeout, layer-based, python3.12, handler `app.lambda_handler`.
- Cron cadences in production: 1 min, 15 min, hourly, daily — all EventBridge cron syntax `cron(m h dom mon dow year)` with `? *` fillers.
