variable "layer_name" {
  description = "Name of the Lambda layer"
  type        = string
}

variable "s3_bucket" {
  description = "S3 bucket where the layer artifact is stored"
  type        = string
}

variable "s3_key" {
  description = "S3 key for the layer artifact (zip file)"
  type        = string
}

variable "compatible_runtimes" {
  description = "List of compatible runtimes"
  type        = list(string)
  default     = ["python3.12"]
}
