########################################
# Scraper Lambda (optional) — container image on ECR
########################################
#
# Chicken-and-egg: Lambda needs an image that lives in ECR, but the image is
# built from this repo. So:
#   1. terraform apply with enable_lambda=true            -> creates the ECR repo
#   2. build + push the image (see terraform/README.md)   -> populates the repo
#   3. set lambda_image_uri=<repo-uri>:latest and re-apply -> creates the function
# The function resource is guarded by local.create_lambda_fn accordingly.

resource "aws_ecr_repository" "scraper" {
  count                = var.enable_lambda ? 1 : 0
  name                 = var.lambda_function_name
  image_tag_mutability = "MUTABLE"
  force_delete         = true

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = {
    Name = "${var.project_name}-scraper"
  }
}

resource "aws_lambda_function" "scraper" {
  count         = local.create_lambda_fn ? 1 : 0
  function_name = var.lambda_function_name
  role          = aws_iam_role.lambda[0].arn
  package_type  = "Image"
  image_uri     = var.lambda_image_uri
  timeout       = var.lambda_timeout
  memory_size   = var.lambda_memory_mb

  environment {
    variables = {
      LOCAL_ENABLED         = "false"
      S3_ENABLED            = var.s3_enabled ? "true" : "false"
      S3_BUCKET             = local.bucket_name
      LOG_DIR               = "/tmp/logs"
      VISITED_STORE_BACKEND = var.create_dynamodb_table ? "dynamodb" : "json"
      VISITED_STORE_PATH    = "/tmp/visited.json"
      DYNAMODB_TABLE        = var.dynamodb_table_name

      # Modulhandbuch classifier: score each download and publish the review
      # manifest to s3://<bucket>/manifests/<job_id>.jsonl for the web app.
      # The model is bundled in the image; only /tmp is writable on Lambda.
      CLASSIFIER_ENABLED  = "true"
      REVIEW_MANIFEST_DIR = "/tmp/review"
    }
  }

  tags = {
    Name = "${var.project_name}-scraper"
  }
}
