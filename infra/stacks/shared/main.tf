# dynasty-bot shared stack
#
# Owns the resources every other dynasty-bot stack depends on, and documents
# the NAMING CONTRACT: cross-stack wiring is name-based data-source lookups
# (tomato pattern), NOT terraform_remote_state. If a name below changes, the
# consuming stacks must change with it.
#
#   Owned HERE (created by this stack):
#     ECR repository        "dynasty-bot"                    -> web stack: data.aws_ecr_repository
#     ACM certificate       dynasty.sarikayakomzin.com       -> web stack: data.aws_acm_certificate
#                                                               (statuses ["ISSUED"], most_recent)
#
#   Reused from tomato (owned by the tomato-shared TFC workspace; looked up
#   here and by the other dynasty-bot stacks BY NAME, never modified):
#     ECS cluster           "tomato-cluster"
#     S3 artifact bucket    "tomato-artifact-bucket"         (dynasty-bot keys live under the
#                                                             "dynasty-bot/" prefix:
#                                                             dynasty-bot/functions/collector.zip,
#                                                             dynasty-bot/layer/layer.zip)
#     IAM roles             "tomato-lambda-exec-role"        (collector Lambda; Atlas-IAM-mapped)
#                           "tomato-ecs-execution-role"      (web task exec)
#                           "tomato-ecs-task-role"           (web task; Atlas-IAM-mapped —
#                                                             MONGODB-AWS auth needs zero secrets)
#     Default VPC + subnets (no custom networking anywhere)
#
#   Names owned by OTHER dynasty-bot stacks (referenced across stacks):
#     Lambda function       "dynasty-bot-collector"          (collector stack; web stack grants
#                                                             lambda:InvokeFunction on exactly it)
#
# ACM / DNS sequencing (no Route53 zone exists in this account — DNS lives at
# an external provider, so validation is MANUAL):
#   1. apply this stack -> cert is created PENDING_VALIDATION; the validation
#      CNAME name/value are outputs below.
#   2. create that CNAME at the external DNS provider; ACM flips the cert to
#      ISSUED (minutes to ~1h).
#   3. only then can the web stack apply: it looks the cert up with
#      statuses = ["ISSUED"], so it fails fast (data source: no matching
#      certificate) instead of hanging half-created.
# Deliberately NO aws_acm_certificate_validation resource here — with manual
# external DNS it would sit and poll until timeout. See infra/README.md.

terraform {
  cloud {
    organization = "goldcoasttrading"

    workspaces {
      name = "dynasty-bot-shared"
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

# --- Reused tomato resources (data sources; see naming contract above) ---

data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

data "aws_ecs_cluster" "tomato" {
  cluster_name = "tomato-cluster"
}

data "aws_s3_bucket" "artifacts" {
  bucket = "tomato-artifact-bucket"
}

data "aws_iam_role" "lambda_exec" {
  name = "tomato-lambda-exec-role"
}

data "aws_iam_role" "ecs_execution" {
  name = "tomato-ecs-execution-role"
}

data "aws_iam_role" "ecs_task" {
  name = "tomato-ecs-task-role"
}

# --- ECR repository ---
#
# Dynasty-bot gets its own repo (the account's only other repo, `tomato`,
# holds tomato's images). Tags are namespaced `<app>-<sha>` / `<app>-latest`
# (today only `web-*`). The lifecycle policy is split per-app prefix, copying
# tomato's hard-won rationale: a previous repo-wide `imageCountMoreThan: 25`
# rule in tomato let a fast-moving app's pushes evict other apps' `-latest`
# tags, silently breaking scheduled runs and leaving long-running services
# unable to restart. Per-prefix rules make one app's churn invisible to
# another's tags.

resource "aws_ecr_repository" "dynasty_bot" {
  name                 = "dynasty-bot"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = false
  }

  encryption_configuration {
    encryption_type = "AES256"
  }
}

resource "aws_ecr_lifecycle_policy" "dynasty_bot" {
  repository = aws_ecr_repository.dynasty_bot.name

  policy = jsonencode({
    rules = [
      for idx, prefix in [
        "web-",
        ] : {
        rulePriority = idx + 1
        description  = "${trimsuffix(prefix, "-")}: keep last 10 images"
        selection = {
          tagStatus     = "tagged"
          tagPrefixList = [prefix]
          countType     = "imageCountMoreThan"
          countNumber   = 10
        }
        action = { type = "expire" }
      }
    ]
  })
}

# --- ACM certificate for the web ALB ---
#
# Improvement over tomato (which passed an out-of-band cert ARN as a TFC
# variable): the cert is IN Terraform, and the manual step is reduced to one
# CNAME at the external DNS provider (outputs below). Sequencing notes are in
# the header comment.

resource "aws_acm_certificate" "web" {
  domain_name       = var.web_hostname
  validation_method = "DNS"

  lifecycle {
    # Standard ACM practice: on replacement, create the new cert before
    # destroying the one an ALB listener may still reference.
    create_before_destroy = true
  }
}
