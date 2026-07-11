########################################
# S3 bucket for scraped output
########################################

resource "aws_s3_bucket" "output" {
  count  = var.create_s3_bucket ? 1 : 0
  bucket = local.bucket_name

  tags = {
    Name = "${var.project_name}-output"
  }
}

resource "aws_s3_bucket_public_access_block" "output" {
  count                   = var.create_s3_bucket ? 1 : 0
  bucket                  = aws_s3_bucket.output[0].id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "output" {
  count  = var.create_s3_bucket ? 1 : 0
  bucket = aws_s3_bucket.output[0].id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}
