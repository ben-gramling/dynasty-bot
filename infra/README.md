# dynasty-bot infra — deploy runbook

Three Terraform Cloud stacks (org `goldcoasttrading`, CLI-driven workspaces
`dynasty-bot-shared` / `dynasty-bot-collector` / `dynasty-bot-web`), all
`us-east-1`, AWS provider pinned `5.55.0` with
`default_tags { project = "dynasty-bot" }`. Cross-stack wiring is name-based
data sources — the naming contract is documented in
`stacks/shared/main.tf`'s header. Reused tomato infra: `tomato-cluster`,
`tomato-artifact-bucket`, `tomato-lambda-exec-role` /
`tomato-ecs-execution-role` / `tomato-ecs-task-role` (the two runtime roles
are Atlas-IAM-mapped, so MONGODB-AWS auth needs zero new secrets).

There is **no Route53 zone in this account** — `sarikayakomzin.com` DNS lives
at an external provider, so two DNS records are created **manually** (steps 2
and 6). This forces the ordering below; do not reorder.

## Order of operations

1. **Apply `shared`** (`just deploy shared`). Creates the `dynasty-bot` ECR
   repo (per-prefix keep-last-10 lifecycle) and the ACM cert for
   `dynasty.sarikayakomzin.com` (status `PENDING_VALIDATION`). Note the
   outputs `acm_validation_cname_name` / `acm_validation_cname_value`.
2. **Manual DNS #1 — cert validation.** At the external DNS provider, create
   the CNAME from those two outputs. ACM flips the cert to `ISSUED`
   (minutes up to ~an hour). There is deliberately **no
   `aws_acm_certificate_validation` resource** — with manual external DNS it
   would just hang an apply until timeout. Check with:
   `aws acm list-certificates --certificate-statuses ISSUED`.
3. **Upload collector artifacts, then apply `collector`.** Build locally
   (`scripts/build_lambda_artifacts.sh`, produces `dist/collector.zip` and
   `dist/layer.zip` for linux/x86_64 cp312), upload to
   `s3://tomato-artifact-bucket/dynasty-bot/functions/collector.zip` and
   `s3://tomato-artifact-bucket/dynasty-bot/layer/layer.zip` (CI does the
   same), then `just deploy collector`. Upload **before** apply — Terraform
   reads the S3 ETags as `source_code_hash` at plan time.
4. **Push the web image.** CI builds `apps/web/Dockerfile` with repo-root
   context and pushes `web-<sha>` + `web-latest` to the `dynasty-bot` ECR
   repo (Docker is CI-only; there is no local docker).
5. **Apply `web`** (`just deploy web`). The stack looks the cert up with
   `data "aws_acm_certificate"` filtered to `statuses = ["ISSUED"]`, so it
   **fails fast** ("no matching certificate") until step 2 has completed —
   that is the guard against attaching an unissued cert to the ALB listener.
6. **Manual DNS #2 — the app hostname.** Create
   `dynasty.sarikayakomzin.com CNAME <alb_dns_name output>` at the external
   provider. (Cognito's callback URL and the cert both assume this hostname;
   the ALB answers only on 443.)
7. **First login.** Cognito user pool `dynasty-bot-user-pool` has one user
   (`bgramling18@gmail.com`, Terraform-provisioned). Cognito emails a
   temporary password on creation; the hosted UI forces a password change on
   first login.

## Day-2 notes

- Redeploys need no manual steps: artifact/image upload then
  `terraform apply` (ETag/tag changes drive the updates); ECS picks up
  `web-latest` on `aws ecs update-service --force-new-deployment`.
- The collector Lambda has **no VPC config on purpose** (public egress to
  Sleeper/KTC). Don't "fix" that without adding a NAT path.
- The Refresh button works because `dynasty-bot-invoke-collector` (inline
  policy on `tomato-ecs-task-role`, added by the web stack) grants
  `lambda:InvokeFunction` on exactly
  `...function:dynasty-bot-collector`. Renaming the Lambda means updating
  `collector_function_name` (collector stack) and `collector_lambda_name`
  (web stack) together.
- Cert renewal: ACM auto-renews DNS-validated certs as long as the validation
  CNAME from step 2 stays in place at the external provider — never delete it.

## Local validation (no cloud access needed)

Per stack/module: `terraform fmt -check -recursive` from `infra/`, and
`terraform init -backend=false && terraform validate` inside each stack.
Never `terraform init` against the cloud backend from a machine that
shouldn't own state operations.
