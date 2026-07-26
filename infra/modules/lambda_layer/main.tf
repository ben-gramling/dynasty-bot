# Lambda layer published from an S3 zip (tomato pattern).
#
# This data source reads the metadata (ETag/hash) of the artifact uploaded by
# CI (or scripts/build_lambda_artifacts.sh + `aws s3 cp`) before apply.

data "aws_s3_object" "layer_zip" {
  bucket = var.s3_bucket
  key    = var.s3_key
}

resource "aws_lambda_layer_version" "this" {
  layer_name          = var.layer_name
  s3_bucket           = var.s3_bucket
  s3_key              = var.s3_key
  compatible_runtimes = var.compatible_runtimes

  # Critical: publish a new layer version ONLY when the content of the S3
  # file (its ETag/hash) changes.
  source_code_hash = data.aws_s3_object.layer_zip.etag
}
