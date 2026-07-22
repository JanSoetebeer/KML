########################################
# IAM — EC2 instance role + (optional) Lambda execution role
########################################

locals {
  bucket_arn = "arn:aws:s3:::${local.bucket_name}"
  lambda_arn = "arn:aws:lambda:${var.aws_region}:${local.account_id}:function:${var.lambda_function_name}"
  dynamo_arn = "arn:aws:dynamodb:${var.aws_region}:${local.account_id}:table/${var.dynamodb_table_name}"

  s3_statements = [
    {
      Sid      = "WebscraperS3"
      Effect   = "Allow"
      Action   = ["s3:PutObject", "s3:GetObject", "s3:ListBucket", "s3:DeleteObject"]
      Resource = [local.bucket_arn, "${local.bucket_arn}/*"]
    }
  ]

  dynamo_statements = var.create_dynamodb_table ? [
    {
      Sid      = "WebscraperDynamoVisited"
      Effect   = "Allow"
      Action   = ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:Scan"]
      Resource = local.dynamo_arn
    }
  ] : []
}

# --- EC2 instance role -----------------------------------------------------

data "aws_iam_policy_document" "ec2_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "ec2" {
  name_prefix        = "${var.project_name}-webapp-"
  assume_role_policy = data.aws_iam_policy_document.ec2_assume.json

  tags = {
    Name = "${var.project_name}-webapp-role"
  }
}

# The web app invokes the scraper Lambda, and (for the optional local scrape /
# S3 file listing) reads/writes the output bucket + visited table.
resource "aws_iam_role_policy" "ec2" {
  name = "${var.project_name}-webapp-policy"
  role = aws_iam_role.ec2.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = concat(
      [
        {
          Sid      = "InvokeScraperLambda"
          Effect   = "Allow"
          Action   = "lambda:InvokeFunction"
          Resource = local.lambda_arn
        }
      ],
      local.s3_statements,
      local.dynamo_statements,
    )
  })
}

resource "aws_iam_instance_profile" "ec2" {
  name_prefix = "${var.project_name}-webapp-"
  role        = aws_iam_role.ec2.name
}

# --- Lambda execution role (optional) --------------------------------------

data "aws_iam_policy_document" "lambda_assume" {
  count = var.enable_lambda ? 1 : 0
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "lambda" {
  count              = var.enable_lambda ? 1 : 0
  name_prefix        = "${var.project_name}-lambda-"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume[0].json

  tags = {
    Name = "${var.project_name}-lambda-role"
  }
}

resource "aws_iam_role_policy_attachment" "lambda_basic" {
  count      = var.enable_lambda ? 1 : 0
  role       = aws_iam_role.lambda[0].name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "lambda" {
  count = var.enable_lambda ? 1 : 0
  name  = "${var.project_name}-lambda-policy"
  role  = aws_iam_role.lambda[0].id

  policy = jsonencode({
    Version   = "2012-10-17"
    Statement = concat(local.s3_statements, local.dynamo_statements)
  })
}
