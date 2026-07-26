# Zip Lambda deployed from S3 (tomato pattern, trimmed of tomato-specific env).
#
# CI (or scripts/build_lambda_artifacts.sh + `aws s3 cp`) uploads the zip
# BEFORE `terraform apply`; the data source below reads the object's ETag so
# Terraform updates the function only when the zip content actually changed.

data "aws_s3_object" "lambda_zip" {
  bucket = var.s3_bucket
  key    = var.s3_key
}

resource "aws_lambda_function" "this" {
  function_name = var.function_name
  handler       = var.handler
  runtime       = var.runtime
  role          = var.iam_role_arn
  layers        = var.layer_arns

  s3_bucket   = var.s3_bucket
  s3_key      = var.s3_key
  timeout     = var.timeout
  memory_size = var.memory_size

  # Tells Terraform to update the function if the S3 file content changes.
  source_code_hash = data.aws_s3_object.lambda_zip.etag

  environment {
    variables = var.lambda_env
  }

  # No vpc_config on purpose: functions using this module need public egress
  # (Sleeper API, KeepTradeCut); a VPC-attached Lambda in the default VPC
  # would have no route to the internet without a NAT gateway.
}

# Tomato leaves Lambda log groups implicitly created (never-expire); we manage
# them so retention matches the repo-wide 30-day convention.
resource "aws_cloudwatch_log_group" "this" {
  name              = "/aws/lambda/${var.function_name}"
  retention_in_days = 30
}
