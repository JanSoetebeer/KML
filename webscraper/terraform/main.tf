########################################
# Shared data sources + locals
########################################

data "aws_caller_identity" "current" {}

# Deploy into the account's default VPC + its subnets, matching the manual
# deployment guide (DEPLOY_WEBAPP_EC2.md). Swap these for explicit VPC/subnet
# variables if you run in a custom network.
data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

# Latest Amazon Linux 2023 AMI (x86_64), resolved via SSM public parameter.
data "aws_ssm_parameter" "al2023" {
  name = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64"
}

locals {
  account_id  = data.aws_caller_identity.current.account_id
  bucket_name = var.s3_bucket_name != "" ? var.s3_bucket_name : "${var.project_name}-output-${local.account_id}"

  # The Lambda function is only materialised once an image URI is supplied.
  create_lambda_fn = var.enable_lambda && var.lambda_image_uri != ""
}
