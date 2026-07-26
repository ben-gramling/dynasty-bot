# REQUIRED

variable "function_name" {
  description = "Name of the Lambda function"
  type        = string
}

variable "iam_role_arn" {
  description = "ARN of the IAM role for the Lambda function"
  type        = string
}

variable "s3_bucket" {
  description = "S3 bucket where the function artifact is stored"
  type        = string
}

variable "s3_key" {
  description = "S3 key for the function artifact (zip file)"
  type        = string
}

variable "cron_schedule" {
  description = "EventBridge cron schedule for invoking the Lambda, e.g. cron(0 10 * * ? *)"
  type        = string
}

# OPTIONAL

variable "layer_arns" {
  description = "List of Lambda Layer ARNs to attach"
  type        = list(string)
  default     = []
}

variable "handler" {
  description = "The function handler (e.g. app.lambda_handler)"
  type        = string
  default     = "app.lambda_handler"
}

variable "runtime" {
  description = "The function runtime"
  type        = string
  default     = "python3.12"
}

variable "timeout" {
  description = "Function timeout in seconds"
  type        = number
  default     = 600
}

variable "memory_size" {
  description = "Function memory in MB"
  type        = number
  default     = 512
}

variable "lambda_env" {
  description = "Environment variables for the function. No defaults on purpose (tomato's default map carried hardcoded webhook URLs and API-key IDs — see the avoid-list in docs/reference-architecture-tomato.md)."
  type        = map(string)
  default     = {}
}
