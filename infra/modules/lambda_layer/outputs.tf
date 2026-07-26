output "layer_arn" {
  description = "The ARN of the created Lambda Layer version"
  value       = aws_lambda_layer_version.this.arn
}
