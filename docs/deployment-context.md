# Deployment-Context Facts: AWS Account, ACM, Route53, Tomato Shared Infra, Atlas Cluster

Verified live on 2026-07-26 via AWS CLI (region us-east-1) and the connected mongodb-atlas MCP server. All four open questions from the tomato analysis are now answered with zero guessing required.

## 1. AWS Credentials / Account

- **Credentials work.** `aws sts get-caller-identity` succeeded.
- Account: **327989636102** (matches expected account).
- Caller: IAM user `arn:aws:iam::327989636102:user/ben-gramling` (UserId `AIDAUYXNUVQDHULBBTADZ`).

## 2. ACM Certificates (us-east-1)

Exactly **one** certificate exists in the account/region:

| Field | Value |
|---|---|
| ARN | `arn:aws:acm:us-east-1:327989636102:certificate/9829e211-afe2-4334-bf38-888f569c813b` |
| Domain | `tomato.sarikayakomzin.com` |
| SANs | `tomato.sarikayakomzin.com` only (no additional SANs) |
| Status | ISSUED, `InUse: true` |
| Type | AMAZON_ISSUED, RSA-2048 |
| Validity | 2026-04-04 → 2026-10-19, RenewalEligibility: ELIGIBLE |

**Key fact: there is NO wildcard `*.sarikayakomzin.com` cert.** The existing cert covers only the tomato hostname and is **not reusable** for a dynasty-bot subdomain (e.g. `dynasty.sarikayakomzin.com`). Dynasty-bot must request its own ACM cert for its hostname (or a wildcard) and complete DNS validation.

## 3. Route53 Hosted Zones

- `aws route53 list-hosted-zones` returned **zero hosted zones** (`"HostedZones": []`).
- **DNS for sarikayakomzin.com is NOT managed in this AWS account.** It lives at an external registrar/DNS provider (consistent with tomato not managing DNS in Terraform).
- Consequences for the build step:
  - Dynasty-bot **cannot** create its subdomain record via Terraform `aws_route53_record` in this account.
  - ACM DNS validation for a new dynasty-bot cert will require a **manual CNAME** at the external DNS provider (same as tomato evidently did — its cert validated and auto-renews via an external validation CNAME).
  - The app's DNS record (CNAME/ALIAS to the load balancer or CloudFront) must also be created manually at the external provider.

## 4. Tomato Shared AWS Resources — Existence Check

All resources the tomato reference doc claims exist were confirmed live:

| Expected resource | Status | Detail |
|---|---|---|
| ECS cluster `tomato-cluster` | **FOUND** | `arn:aws:ecs:us-east-1:327989636102:cluster/tomato-cluster` — the only ECS cluster in the region |
| ECR repo `tomato` | **FOUND** | `327989636102.dkr.ecr.us-east-1.amazonaws.com/tomato`, created 2025-11-08, MUTABLE tags, AES256; the **only** ECR repo — dynasty-bot needs its own repo (or must share, which would mix image tags) |
| S3 `tomato-artifact-bucket` | **FOUND** | created 2025-10-21. Other buckets in account: `tomato-model-bucket` (2025-11-07), `arbriver-bucket` (2024-07-19) |
| IAM role `tomato-ecs-task-role` | **FOUND** | `arn:aws:iam::327989636102:role/tomato-ecs-task-role`, RoleId `AROAUYXNUVQDC6DQDMQ6X`, created 2026-04-04; trust policy allows `ecs-tasks.amazonaws.com` to assume; `RoleLastUsed` 2026-07-26 (us-east-1) — **actively in use right now** |

The `tomato-ecs-task-role` last-used timestamp being today confirms the tomato service is live; this is the role whose Atlas IAM mapping dynasty-bot would piggyback on for MONGODB-AWS auth (a dynasty-bot task using this same task role would authenticate to Atlas with no new secrets). Alternatively, a dedicated dynasty-bot task role would need its own Atlas database-user IAM mapping added in Atlas.

## 5. Atlas Cluster Contents

- **Connected cluster host: `tributary-dev.ygqeljj.mongodb.net`** (confirmed from the MCP server's configured `mongodb+srv://` connection string, not inferred). This is the same shared cluster tomato uses.
- Databases present (`list-databases`, 9 total):

| Database | Size (bytes) |
|---|---|
| admin | 368,640 |
| arbriver | 1,114,112 |
| arbriver-dev | 483,328 |
| config | 581,632 |
| kxrt | 14,434,304 |
| kxrt-integration | 196,608 |
| kxrt-training | 1,013,305,344 |
| local | 664,178,688 |
| tomato_backtest | 110,592 |

- Expected marker databases `kxrt` and `kxrt-training` are **both present** — cluster identity double-confirmed.
- **No `dynasty-bot` (or similarly named) database exists yet.** Dynasty-bot would create a fresh database on this shared cluster; MongoDB creates it implicitly on first write, so no provisioning step is needed beyond auth.

## Reuse-vs-Provision Decision Inputs (summary)

| Item | Verdict |
|---|---|
| AWS account/creds | Reuse — working, account 327989636102 |
| ACM cert | **Provision new** — existing cert is single-host `tomato.sarikayakomzin.com`, no wildcard |
| Route53 zone | **Not available** — no zone in account; DNS records and cert-validation CNAMEs must be created manually at the external DNS provider |
| ECS cluster | Reuse `tomato-cluster` (exists, live) |
| ECR repo | **Provision new** — only `tomato` repo exists |
| Artifact bucket | Reuse `tomato-artifact-bucket` (exists) |
| ECS task role / Atlas IAM auth | Reuse `tomato-ecs-task-role` (exists, actively used today) or provision a dedicated role + Atlas IAM mapping |
| Atlas cluster | Reuse `tributary-dev.ygqeljj.mongodb.net`; `dynasty-bot` database does not exist yet and will be created on first write |
