# Informational outputs. The other dynasty-bot stacks do NOT consume these via
# terraform_remote_state — they look resources up by name (see the naming
# contract in main.tf). The ACM validation outputs are the one pair a human
# actually needs: they are the manual CNAME to create at the external DNS
# provider.

output "ecr_repo_url" {
  description = "URL of the dynasty-bot ECR repository (CI pushes web-<sha> / web-latest here)"
  value       = aws_ecr_repository.dynasty_bot.repository_url
}

output "acm_certificate_arn" {
  description = "ARN of the dynasty-bot web certificate (PENDING_VALIDATION until the CNAME below exists)"
  value       = aws_acm_certificate.web.arn
}

output "acm_validation_cname_name" {
  description = "MANUAL STEP - create this CNAME record name at the external DNS provider to validate the cert"
  value       = tolist(aws_acm_certificate.web.domain_validation_options)[0].resource_record_name
}

output "acm_validation_cname_value" {
  description = "MANUAL STEP - the value the validation CNAME must point to"
  value       = tolist(aws_acm_certificate.web.domain_validation_options)[0].resource_record_value
}

output "acm_validation_record_type" {
  description = "Record type for the validation record (always CNAME for DNS validation)"
  value       = tolist(aws_acm_certificate.web.domain_validation_options)[0].resource_record_type
}

output "artifacts_bucket" {
  description = "Shared tomato artifact bucket; dynasty-bot artifacts live under the dynasty-bot/ prefix"
  value       = data.aws_s3_bucket.artifacts.bucket
}

output "ecs_cluster_arn" {
  value = data.aws_ecs_cluster.tomato.arn
}

output "lambda_exec_role_arn" {
  value = data.aws_iam_role.lambda_exec.arn
}

output "ecs_execution_role_arn" {
  value = data.aws_iam_role.ecs_execution.arn
}

output "ecs_task_role_arn" {
  value = data.aws_iam_role.ecs_task.arn
}

output "vpc_id" {
  value = data.aws_vpc.default.id
}

output "subnet_ids" {
  value = data.aws_subnets.default.ids
}
