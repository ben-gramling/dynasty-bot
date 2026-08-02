# dynasty-bot collector stack
#
# One zip Lambda (`dynasty-bot-collector`, python3.12, app.lambda_handler,
# daily EventBridge cron + on-demand invokes from the web Refresh button) plus
# its dependency layer. Artifacts are built by scripts/build_lambda_artifacts.sh
# and land in the EXISTING tomato-artifact-bucket under the dynasty-bot/ key
# prefix; the modules read the S3 ETag as source_code_hash, so the CI order is
# always upload-then-apply.
#
# NO vpc_config on the Lambda (module never sets one): it needs public egress
# to the Sleeper API and KeepTradeCut, and a default-VPC Lambda would have no
# internet route without a NAT gateway.
#
# Auth: the reused tomato-lambda-exec-role is already mapped to an Atlas
# database user, so the MONGODB-AWS URI below carries no credentials at all.

terraform {
  cloud {
    organization = "goldcoasttrading"

    workspaces {
      name = "dynasty-bot-collector"
    }
  }
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "5.55.0"
    }
  }
  required_version = ">= 1.1.0"
}

provider "aws" {
  region = "us-east-1"

  default_tags {
    tags = {
      project = "dynasty-bot"
    }
  }
}

# --- Look up shared resources (naming contract: infra/stacks/shared/main.tf) ---

data "aws_iam_role" "lambda_exec" {
  name = "tomato-lambda-exec-role"
}

# --- Lambda layer: core wheel + runtime deps (httpx, pymongo[aws], dotenv) ---
#
# Built for linux/x86_64 cp312 by scripts/build_lambda_artifacts.sh (pymongo
# ships C extensions — a wrong-platform build crashes at import time).

module "deps_layer" {
  source = "../../modules/lambda_layer"

  layer_name = "dynasty-bot-deps"
  s3_bucket  = var.artifacts_s3_bucket
  s3_key     = var.layer_s3_key
}

# --- Collector Lambda ---

module "collector" {
  source = "../../modules/lambda_function"

  function_name = var.collector_function_name
  iam_role_arn  = data.aws_iam_role.lambda_exec.arn
  s3_bucket     = var.artifacts_s3_bucket
  s3_key        = var.collector_s3_key
  layer_arns    = [module.deps_layer.layer_arn]

  handler = "app.lambda_handler"
  runtime = "python3.12"
  timeout = 900

  # v6 sizes this, not the old 512. The nightly board now enumerates the fair
  # band COMPLETELY (no fleece bracket, no variant cap) instead of sampling ~2
  # gets per (counterparty, give, count-signature): measured 479 MB peak RSS
  # and 54 s for the |favor| ≤ 5 pool on the live snapshot, against 162 MB /
  # 14 s for the capped one. 2048 MB leaves real headroom for roster growth —
  # 512 would OOM and 1024 would sit one bad snapshot away from it. Lambda also
  # scales CPU with memory, so this buys throughput on the pool build too.
  # Timeout goes to 900 (the service maximum) for the same reason: the build is
  # a third of the old 600 s ceiling before any search work happens.
  memory_size = 2048

  # Daily at 10:00 UTC.
  cron_schedule = "cron(0 10 * * ? *)"

  lambda_env = {
    # MONGODB-AWS IAM auth: no credentials in the URI; the Lambda's exec role
    # IS the credential. The DB is selected by MONGODB_DB, NEVER the URI path
    # (the /arbriver path segment is a quirk of how the Atlas AWS-auth user
    # was originally set up for tomato and is explicitly unused).
    MONGODB_URI = var.mongodb_uri
    MONGODB_DB  = "dynasty-bot"
  }
}
