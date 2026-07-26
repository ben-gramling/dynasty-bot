variable "collector_function_name" {
  type        = string
  description = "Name of the collector Lambda. The web stack scopes its lambda:InvokeFunction grant to exactly this name — change both together."
  default     = "dynasty-bot-collector"
}

variable "artifacts_s3_bucket" {
  type        = string
  description = "Shared artifact bucket (owned by tomato-shared); dynasty-bot artifacts live under the dynasty-bot/ prefix"
  default     = "tomato-artifact-bucket"
}

variable "collector_s3_key" {
  type        = string
  description = "S3 key of the collector function zip"
  default     = "dynasty-bot/functions/collector.zip"
}

variable "layer_s3_key" {
  type        = string
  description = "S3 key of the dependency layer zip"
  default     = "dynasty-bot/layer/layer.zip"
}

variable "mongodb_uri" {
  type        = string
  description = "MONGODB-AWS (IAM auth) connection string — contains no secret; the exec role is the credential. Same shape as tomato's task definitions."
  default     = "mongodb+srv://tributary-dev.ygqeljj.mongodb.net/arbriver?authSource=$external&authMechanism=MONGODB-AWS"
}
