# dynasty-bot web stack
#
# Next.js dashboard on ECS Fargate (tomato-cluster) behind a new 443-only ALB
# with Cognito auth (single user). Mirrors tomato's dashboard stack with the
# planned improvements: default_tags, no hardcoded ARNs/URIs in resources,
# Terraform-owned ACM cert (in the shared stack), and an exact-ARN IAM grant.
#
# APPLY ORDER (see infra/README.md):
#   1. shared stack applied and the ACM validation CNAME created at the
#      external DNS provider; the cert must be ISSUED. The data source below
#      filters on statuses = ["ISSUED"], so this stack FAILS FAST ("no
#      matching certificate") until that has happened — deliberate, an ALB
#      listener cannot attach a pending cert anyway.
#   2. collector stack applied (the task env references the collector Lambda
#      by name and the invoke grant builds its ARN by convention — the button
#      500s until the function exists).
#   3. CI pushed the web image (web-latest) to the dynasty-bot ECR repo.
#   4. apply this stack, then create the LAST manual DNS record:
#      dynasty.sarikayakomzin.com CNAME -> alb_dns_name output.

terraform {
  cloud {
    organization = "goldcoasttrading"

    workspaces {
      name = "dynasty-bot-web"
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

data "aws_caller_identity" "current" {}

data "aws_region" "current" {}

data "aws_ecs_cluster" "tomato" {
  cluster_name = "tomato-cluster"
}

data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

data "aws_iam_role" "ecs_execution" {
  name = "tomato-ecs-execution-role"
}

data "aws_iam_role" "ecs_task" {
  name = "tomato-ecs-task-role"
}

data "aws_ecr_repository" "dynasty_bot" {
  name = "dynasty-bot"
}

# Fails until the shared-stack cert has been DNS-validated at the external
# provider and is ISSUED — the fail-fast gate described in the header.
data "aws_acm_certificate" "web" {
  domain      = var.hostname
  statuses    = ["ISSUED"]
  most_recent = true
}

# --- Cognito (single-user auth at the ALB, tomato dashboard pattern) ---

resource "aws_cognito_user_pool" "web" {
  name = "dynasty-bot-user-pool"

  auto_verified_attributes = ["email"]

  schema {
    name                = "email"
    attribute_data_type = "String"
    required            = true
    mutable             = true
  }
}

resource "aws_cognito_user_pool_client" "web" {
  name                                 = "dynasty-bot-alb-client"
  user_pool_id                         = aws_cognito_user_pool.web.id
  generate_secret                      = true
  allowed_oauth_flows                  = ["code"]
  allowed_oauth_scopes                 = ["openid"]
  allowed_oauth_flows_user_pool_client = true
  callback_urls                        = ["https://${var.hostname}/oauth2/idpresponse"]
  supported_identity_providers         = ["COGNITO"]
}

resource "aws_cognito_user_pool_domain" "web" {
  domain       = "dynasty-bot"
  user_pool_id = aws_cognito_user_pool.web.id
}

# The entire user base: one Terraform-provisioned user.
resource "aws_cognito_user" "owner" {
  user_pool_id = aws_cognito_user_pool.web.id
  username     = var.cognito_user_email

  attributes = {
    email          = var.cognito_user_email
    email_verified = true
  }
}

# --- ALB ---

resource "aws_security_group" "alb" {
  name        = "dynasty-bot-alb-sg"
  description = "dynasty-bot web ALB - allow HTTPS inbound"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_lb" "web" {
  name               = "dynasty-bot-alb"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb.id]
  subnets            = data.aws_subnets.default.ids
}

resource "aws_lb_target_group" "web" {
  name        = "dynasty-bot-web-tg"
  port        = 3000
  protocol    = "HTTP"
  vpc_id      = data.aws_vpc.default.id
  target_type = "ip"

  # NOT "/" — the app's "/" answers with a redirect to /waivers (307), which a
  # default 200 matcher marks unhealthy and cycles the task forever.
  # /api/run-status is a real 200 JSON endpoint; it also returns 503 when the
  # DB is unreachable, so unhealthy_threshold is loosened to ride out a brief
  # Atlas primary election without recycling the task.
  health_check {
    path                = "/api/run-status"
    matcher             = "200"
    interval            = 30
    timeout             = 5
    healthy_threshold   = 2
    unhealthy_threshold = 5
  }
}

resource "aws_lb_listener" "https" {
  load_balancer_arn = aws_lb.web.arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn   = data.aws_acm_certificate.web.arn

  # Ordered default actions: every request must pass Cognito login first.
  default_action {
    type = "authenticate-cognito"

    authenticate_cognito {
      user_pool_arn       = aws_cognito_user_pool.web.arn
      user_pool_client_id = aws_cognito_user_pool_client.web.id
      user_pool_domain    = aws_cognito_user_pool_domain.web.domain
    }
  }

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.web.arn
  }
}

# --- CloudWatch ---

resource "aws_cloudwatch_log_group" "web" {
  name              = "/ecs/web"
  retention_in_days = 30
}

# --- Security group (ECS task): 3000 from the ALB SG only ---

resource "aws_security_group" "web" {
  name        = "dynasty-bot-web-sg"
  description = "dynasty-bot web ECS task - allow traffic from ALB only"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    from_port       = 3000
    to_port         = 3000
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# --- Refresh-button IAM: exact-ARN invoke grant on the shared task role ---
#
# The web task runs as tomato-ecs-task-role (reused for its Atlas IAM
# mapping). A SEPARATE inline role policy adds lambda:InvokeFunction scoped to
# ONLY the dynasty-bot collector function: attaching a new named policy does
# not disturb tomato's Terraform state (tomato manages its own attachments),
# and removing this stack cleanly removes the grant. ARN is built by
# convention (var.collector_lambda_name) rather than a data source so this
# stack has no hard plan-time dependency on the collector stack.

resource "aws_iam_role_policy" "invoke_collector" {
  name = "dynasty-bot-invoke-collector"
  role = data.aws_iam_role.ecs_task.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["lambda:InvokeFunction"]
      Resource = ["arn:aws:lambda:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:function:${var.collector_lambda_name}"]
    }]
  })
}

# --- ECS task definition ---

resource "aws_ecs_task_definition" "web" {
  family                   = "dynasty-bot-web"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = "512"
  memory                   = "1024"
  execution_role_arn       = data.aws_iam_role.ecs_execution.arn
  task_role_arn            = data.aws_iam_role.ecs_task.arn

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }

  container_definitions = jsonencode([
    {
      name      = "web"
      image     = "${data.aws_ecr_repository.dynasty_bot.repository_url}:${var.image_tag}"
      essential = true
      portMappings = [
        {
          containerPort = 3000
          protocol      = "tcp"
        }
      ]
      environment = [
        {
          # MONGODB-AWS IAM auth — the task role is the credential; the DB is
          # selected by MONGODB_DB, never the URI path (/arbriver is an unused
          # quirk of the original Atlas AWS-auth user).
          name  = "MONGODB_URI"
          value = var.mongodb_uri
        },
        {
          name  = "MONGODB_DB"
          value = "dynasty-bot"
        },
        {
          name  = "NODE_ENV"
          value = "production"
        },
        {
          # Refresh button target (server action -> lambda:InvokeFunction).
          name  = "COLLECTOR_LAMBDA_NAME"
          value = var.collector_lambda_name
        },
        {
          # Fargate does not reliably inject AWS_REGION for SDK v3 — without
          # it the LambdaClient in the server action can fail region
          # resolution at runtime.
          name  = "AWS_REGION"
          value = data.aws_region.current.name
        },
      ]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.web.name
          "awslogs-region"        = data.aws_region.current.name
          "awslogs-stream-prefix" = "ecs"
        }
      }
    }
  ])
}

# --- ECS service ---

resource "aws_ecs_service" "web" {
  name            = "dynasty-bot-web"
  cluster         = data.aws_ecs_cluster.tomato.id
  task_definition = aws_ecs_task_definition.web.arn
  launch_type     = "FARGATE"
  desired_count   = 1

  network_configuration {
    subnets         = data.aws_subnets.default.ids
    security_groups = [aws_security_group.web.id]
    # Default VPC, no NAT: the public IP provides egress (Atlas, ECR pulls).
    assign_public_ip = true
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.web.arn
    container_name   = "web"
    container_port   = 3000
  }
}
