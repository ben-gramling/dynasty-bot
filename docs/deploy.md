# Deploy Runbook

First-time deploy of dynasty-bot to AWS (account `327989636102`, `us-east-1`).
Ordering is strict because DNS for `sarikayakomzin.com` lives at an external
provider (no Route53 zone in the account) — two manual CNAMEs gate the flow.
Day-2 operational notes live in `infra/README.md`.

Everything below is copy-pasteable from the repo root unless noted.

## 0. Prerequisites

| Check | How |
|---|---|
| Terraform ≥ 1.1 installed | `terraform version` |
| Logged in to Terraform Cloud | `test -f ~/.terraform.d/credentials.tfrc.json && echo ok` — if missing, run `terraform login`. (Verified present on the dev WSL box 2026-07-26. Never print this file.) |
| Member of TFC org `goldcoasttrading` | app.terraform.io → org switcher |
| AWS CLI works against the right account | `aws sts get-caller-identity` → account `327989636102` |
| External DNS provider access | You can create CNAMEs for `sarikayakomzin.com` (needed twice: steps 2 and 6) |
| Artifact build tools | `uv`, `python3.12` (no Docker needed for the Lambda artifacts) |

**AWS creds for Terraform runs — tomato's arrangement, copied.** TFC
workspaces are CLI-driven with **remote execution**; tomato's CI hands
Terraform only `TF_API_TOKEN` (`hashicorp/setup-terraform` +
`cli_config_credentials_token`), so the AWS provider gets its credentials
from **workspace environment variables inside TFC**, not from the caller.
Set `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` (category *env*, marked
*sensitive*) on each of the three workspaces — or once via a TFC variable
set attached to all three.

**GitHub repo secrets** (for CI, same trio tomato uses):
`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` (static keys — artifact/image
pushes), `TF_API_TOKEN` (TFC remote runs).

## 1. Terraform Cloud workspaces

Create three **CLI-driven** workspaces in org `goldcoasttrading` (UI: New
workspace → CLI-driven workflow), or let the first `terraform init` in each
stack dir offer to create them:

| Workspace | Stack dir |
|---|---|
| `dynasty-bot-shared` | `infra/stacks/shared` |
| `dynasty-bot-collector` | `infra/stacks/collector` |
| `dynasty-bot-web` | `infra/stacks/web` |

**REQUIRED — set each workspace's Working Directory to its stack dir** (UI:
Settings → General → Terraform Working Directory, or the API
`working-directory` attribute; tomato's workspaces are configured the same
way). Without it, remote runs upload only the stack folder, the
`../../modules` references aren't in the config slug, and `terraform init`
fails on TFC with `Unreadable module directory` (collector/web use modules;
shared happens to work because it uses none — this bit us on first deploy,
2026-07-26).

Per-workspace variables:

- **Env vars (all three workspaces):** `AWS_ACCESS_KEY_ID`,
  `AWS_SECRET_ACCESS_KEY` — sensitive; value = the deploy IAM user's static
  keys (same keys as the GitHub secrets). Nothing else — MONGODB-AWS IAM
  auth means no DB password exists anywhere.
- **Terraform variables:** none required — every variable has a working
  default. Override only if you know why:
  - `shared`: `web_hostname` (default `dynasty.sarikayakomzin.com`).
  - `collector`: `collector_function_name`, `artifacts_s3_bucket`,
    `collector_s3_key`, `layer_s3_key`, `mongodb_uri` (the credential-free
    `authMechanism=MONGODB-AWS` URI; DB is selected by env `MONGODB_DB`,
    never the URI path).
  - `web`: `image_tag` (default `web-latest`), `hostname`,
    `cognito_user_email` (default `bgramling18@gmail.com`),
    `collector_lambda_name`, `mongodb_uri`. Rename the Lambda only by
    changing `collector_function_name` + `collector_lambda_name` together.

## 2. Apply, in this exact order

### 2.1 shared → manual cert-validation CNAME → wait for ISSUED

```sh
just deploy shared        # = cd infra/stacks/shared && terraform apply
cd infra/stacks/shared
terraform output -raw acm_validation_cname_name;  echo
terraform output -raw acm_validation_cname_value; echo
```

At the external DNS provider create that CNAME (name → value, TTL
whatever). There is deliberately **no `aws_acm_certificate_validation`
resource** — it would hang the apply waiting on manual DNS. Poll until
`ISSUED` (minutes up to ~an hour):

```sh
aws acm describe-certificate \
  --certificate-arn "$(cd infra/stacks/shared && terraform output -raw acm_certificate_arn)" \
  --query Certificate.Status --output text
```

Leave the validation CNAME in place forever — ACM auto-renewal depends on it.

### 2.2 collector — upload artifacts FIRST, then apply

Terraform reads the S3 ETags as `source_code_hash` at plan time, so upload
before apply (CI's `collector.yml` enforces the same order with `needs:`):

```sh
./scripts/build_lambda_artifacts.sh   # dist/collector.zip (~3K) + dist/layer.zip (~18M), linux/x86_64 cp312
aws s3 cp dist/collector.zip s3://tomato-artifact-bucket/dynasty-bot/functions/collector.zip
aws s3 cp dist/layer.zip     s3://tomato-artifact-bucket/dynasty-bot/layer/layer.zip
just deploy collector
```

Creates layer `dynasty-bot-deps` + function `dynasty-bot-collector`
(python3.12, 600s/512MB, **no VPC on purpose** — public egress to
Sleeper/KTC) on daily `cron(0 10 * * ? *)` (10:00 UTC).

### 2.3 web image — CI on merge, or manual bootstrap

On merge to `main`, CI (`web.yml` → `deploy-ecs.yml`) builds
`apps/web/Dockerfile` (repo-root context, BuildKit — it honors
`apps/web/Dockerfile.dockerignore`) and pushes `web-<sha>` + `web-latest`.
First-time bootstrap from any Docker-capable machine (local WSL has no
Docker):

```sh
aws ecr get-login-password --region us-east-1 \
  | docker login --username AWS --password-stdin 327989636102.dkr.ecr.us-east-1.amazonaws.com
ECR=327989636102.dkr.ecr.us-east-1.amazonaws.com/dynasty-bot
docker build -f apps/web/Dockerfile -t $ECR:web-$(git rev-parse HEAD) -t $ECR:web-latest .
docker push $ECR:web-$(git rev-parse HEAD) && docker push $ECR:web-latest
```

### 2.4 web

```sh
just deploy web
```

The stack looks the cert up with `data "aws_acm_certificate"`
(`statuses = ["ISSUED"]`), so it **fails fast with "no matching
certificate" until 2.1 is fully done** — that error means "go finish the
validation CNAME", not that the stack is broken. Creates ALB
`dynasty-bot-alb` (443-only, authenticate-cognito → forward; target-group
health check is `/api/run-status` matcher 200 — "/" redirects and would
flap), Cognito pool `dynasty-bot-user-pool` + one user, and ECS service
`dynasty-bot-web` on `tomato-cluster`. The service flaps until 2.3's image
exists; the Refresh button needs 2.2's Lambda.

### 2.5 manual app CNAME

```sh
cd infra/stacks/web && terraform output -raw alb_dns_name
```

At the external DNS provider: `dynasty.sarikayakomzin.com CNAME <that
value>`. The cert, the Cognito callback, and the 443-only listener all
assume this exact hostname.

## 3. First login (Cognito)

Applying the web stack creates user `bgramling18@gmail.com`; Cognito emails
a **temporary password** (from `no-reply@verificationemail.com` — check
spam). Browse to <https://dynasty.sarikayakomzin.com> → hosted UI → sign in
with the temp password → forced password change → redirected to the app.
Temp passwords expire after ~7 days; if expired, reset without email:

```sh
POOL=$(aws cognito-idp list-user-pools --max-results 20 \
  --query "UserPools[?Name=='dynasty-bot-user-pool'].Id" --output text)
aws cognito-idp admin-set-user-password --user-pool-id "$POOL" \
  --username bgramling18@gmail.com --password '<new-password>' --permanent
```

## 4. Smoke checks

```sh
# 1. ALB up + auth gate on: expect 302 to https://dynasty-bot.auth.us-east-1.amazoncognito.com/...
curl -sI https://dynasty.sarikayakomzin.com/ | head -4

# 2. Target healthy (ALB probes /api/run-status directly, bypassing Cognito)
aws elbv2 describe-target-health \
  --target-group-arn "$(aws elbv2 describe-target-groups --names dynasty-bot-web-tg \
      --query 'TargetGroups[0].TargetGroupArn' --output text)" \
  --query 'TargetHealthDescriptions[].TargetHealth.State'

# 3. In the logged-in browser: /api/run-status returns JSON; header shows last run; press Refresh.

# 4. Collector actually ran (Refresh or the 10:00 UTC cron):
aws logs tail /aws/lambda/dynasty-bot-collector --since 30m
# (fire one manually: aws lambda invoke --function-name dynasty-bot-collector \
#    --invocation-type Event --payload '{}' /dev/null)

# 5. Run log landed in Mongo (local user/pass URI from the repo-root .env):
mongosh "$MONGODB_URI" --quiet --eval \
  'db.getSiblingDB("dynasty-bot").runs.countDocuments()'
# or via the mongodb-atlas MCP: count { database: "dynasty-bot", collection: "runs" }
```

## 5. Rollback

**Web — bad image.** Re-point `web-latest` at a known-good sha (no Docker
needed) and bounce the service:

```sh
MANIFEST=$(aws ecr batch-get-image --repository-name dynasty-bot \
  --image-ids imageTag=web-<good-sha> --query 'images[0].imageManifest' --output text)
aws ecr put-image --repository-name dynasty-bot --image-tag web-latest --image-manifest "$MANIFEST"
aws ecs update-service --cluster tomato-cluster --service dynasty-bot-web --force-new-deployment
```

**Web — bad task definition.** `aws ecs update-service --cluster
tomato-cluster --service dynasty-bot-web --task-definition
dynasty-bot-web:<previous-rev>` (list revs:
`aws ecs list-task-definitions --family-prefix dynasty-bot-web`). Note:
the next `terraform apply` reverts to Terraform's recorded revision — make
the fix permanent in code.

**Collector.** Check out the good commit, rebuild, re-upload, re-apply —
the changed S3 ETag re-points the function:

```sh
git checkout <good-sha> -- apps/collector libs/core
./scripts/build_lambda_artifacts.sh
aws s3 cp dist/collector.zip s3://tomato-artifact-bucket/dynasty-bot/functions/collector.zip
aws s3 cp dist/layer.zip     s3://tomato-artifact-bucket/dynasty-bot/layer/layer.zip
just deploy collector
```

(Emergency shortcut after the s3 cp: `aws lambda update-function-code
--function-name dynasty-bot-collector --s3-bucket tomato-artifact-bucket
--s3-key dynasty-bot/functions/collector.zip` — Terraform reconciles on the
next apply.)

## 6. Costs (rough, us-east-1, monthly)

| Resource | Est./mo |
|---|---|
| Fargate 0.5 vCPU / 1 GB, 24/7 (~730 h) | ~$18 |
| ALB hours ($0.0225/h) + minimal LCU | ~$17 |
| Public IPv4 ($0.005/h × ~3: 2 ALB AZs + 1 task) | ~$11 |
| Lambda (1 run/day ≤600s @512MB) + EventBridge | ~$0 (free tier) |
| Cognito (1 MAU) | $0 |
| ECR (keep-last-10 × ~200MB layers) + S3 artifacts | <$1 |
| CloudWatch logs (30-day retention, low volume) | <$1 |
| **Total** | **~$47** |

Fargate + ALB + IPv4 dominate; everything else is noise. The one lever:
stopping the web service (`desired_count = 0`) when unused saves ~$22/mo
(task + its IP), while the ALB keeps costing ~$28/mo as long as it exists.
