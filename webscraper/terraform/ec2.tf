########################################
# EC2 web app instance + Elastic IP
########################################

# Signing key for session tokens. Generated once and kept in Terraform state
# (mark state sensitive / store it in a secure backend). Override by setting a
# SECRET_KEY yourself in the .env if you prefer.
resource "random_password" "secret_key" {
  length  = 48
  special = false
}

resource "aws_key_pair" "this" {
  count      = var.ssh_public_key != "" ? 1 : 0
  key_name   = "${var.project_name}-key"
  public_key = var.ssh_public_key
}

# Allocate the Elastic IP first (without an instance) so its public address is
# known and can be injected into user_data as SITE_ADDRESS — Caddy needs the
# concrete IP to provision its self-signed certificate. The association below
# then binds it to the instance (no dependency cycle).
resource "aws_eip" "webapp" {
  domain = "vpc"

  tags = {
    Name = "${var.project_name}-webapp-eip"
  }
}

resource "aws_instance" "webapp" {
  ami                    = data.aws_ssm_parameter.al2023.value
  instance_type          = var.instance_type
  subnet_id              = data.aws_subnets.default.ids[0]
  vpc_security_group_ids = [aws_security_group.webapp.id]
  iam_instance_profile   = aws_iam_instance_profile.ec2.name
  key_name               = var.ssh_public_key != "" ? aws_key_pair.this[0].key_name : null

  user_data_replace_on_change = true
  user_data = templatefile("${path.module}/user_data.sh.tftpl", {
    repo_url                = var.repo_url
    repo_branch             = var.repo_branch
    repo_subdir             = var.repo_subdir
    secret_key              = random_password.secret_key.result
    session_max_age_seconds = var.session_max_age_seconds
    admin_username          = var.admin_username
    admin_password          = var.admin_password
    site_address            = aws_eip.webapp.public_ip
    lambda_function_name    = var.lambda_function_name
    aws_region              = var.aws_region
    s3_enabled              = var.s3_enabled ? "true" : "false"
    s3_bucket               = local.bucket_name
    visited_backend         = var.create_dynamodb_table ? "dynamodb" : "json"
    dynamodb_table          = var.dynamodb_table_name
  })

  metadata_options {
    http_endpoint = "enabled"
    http_tokens   = "required"
    # >1 so boto3 running *inside a Docker container* can still reach IMDSv2
    # (each container network hop decrements the TTL).
    http_put_response_hop_limit = 2
  }

  root_block_device {
    volume_size = var.root_volume_size
    volume_type = "gp3"
    encrypted   = true
  }

  tags = {
    Name = "${var.project_name}-webapp"
  }
}

resource "aws_eip_association" "webapp" {
  instance_id   = aws_instance.webapp.id
  allocation_id = aws_eip.webapp.id
}
