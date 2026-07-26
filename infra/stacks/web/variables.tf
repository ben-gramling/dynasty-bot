variable "image_tag" {
  type        = string
  description = "Image tag in the dynasty-bot ECR repo (CI pushes web-<sha> and web-latest)"
  default     = "web-latest"
}

variable "hostname" {
  type        = string
  description = "Public hostname (must match the shared-stack ACM cert domain; DNS CNAME to the ALB is manual at the external provider)"
  default     = "dynasty.sarikayakomzin.com"
}

variable "cognito_user_email" {
  type        = string
  description = "Email address for the single dashboard user"
  default     = "bgramling18@gmail.com"
}

variable "collector_lambda_name" {
  type        = string
  description = "Name of the collector Lambda the Refresh button invokes (naming contract with the collector stack)"
  default     = "dynasty-bot-collector"
}

variable "mongodb_uri" {
  type        = string
  description = "MONGODB-AWS (IAM auth) connection string — contains no secret; the task role is the credential. Same shape as tomato's task definitions."
  default     = "mongodb+srv://tributary-dev.ygqeljj.mongodb.net/arbriver?authSource=$external&authMechanism=MONGODB-AWS"
}
