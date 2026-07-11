########################################
# General
########################################

variable "aws_region" {
  description = "AWS region to deploy into."
  type        = string
  default     = "eu-central-1"
}

variable "project_name" {
  description = "Name prefix applied to all created resources and tags."
  type        = string
  default     = "webscraper"
}

########################################
# EC2 web app
########################################

variable "instance_type" {
  description = "EC2 instance type. t3.small (2 GB) is the sensible minimum for Docker + Caddy + uvicorn."
  type        = string
  default     = "t3.small"
}

variable "root_volume_size" {
  description = "Root EBS volume size in GiB. Scraped files can be large if LOCAL storage is used."
  type        = number
  default     = 20
}

variable "ssh_public_key" {
  description = <<-EOT
    Contents of an SSH *public* key (e.g. the text of ~/.ssh/id_ed25519.pub).
    Terraform registers it as an EC2 key pair so you can SSH in with the matching
    private key. Leave empty to launch the instance without a key pair.
  EOT
  type        = string
  default     = ""
}

variable "ssh_ingress_cidr" {
  description = "CIDR allowed to reach SSH (port 22). Set this to <your-ip>/32 — never 0.0.0.0/0."
  type        = string
}

variable "web_ingress_cidr" {
  description = "CIDR allowed to reach the web app over HTTP/HTTPS (80/443)."
  type        = string
  default     = "0.0.0.0/0"
}

########################################
# App configuration (baked into the instance .env by user_data)
########################################

variable "admin_username" {
  description = "Seed admin username, applied only on first DB creation."
  type        = string
  default     = "admin"
}

variable "admin_password" {
  description = "Seed admin password, applied only on first DB creation. Provide a strong value (e.g. via TF_VAR_admin_password)."
  type        = string
  sensitive   = true
}

variable "session_max_age_seconds" {
  description = "Session token lifetime in seconds."
  type        = number
  default     = 43200
}

variable "repo_url" {
  description = "Git URL the instance clones to obtain the application code (must contain the webscraper/ directory)."
  type        = string
}

variable "repo_subdir" {
  description = "Sub-directory within the cloned repo that holds docker-compose.yml (the webscraper project)."
  type        = string
  default     = "webscraper"
}

variable "repo_branch" {
  description = "Git branch to check out."
  type        = string
  default     = "main"
}

########################################
# Storage / dedup backends
########################################

variable "create_s3_bucket" {
  description = "Create the S3 bucket that stores scraped files."
  type        = bool
  default     = true
}

variable "s3_bucket_name" {
  description = "Name of the scraped-output S3 bucket. Empty => <project>-output-<account_id>."
  type        = string
  default     = ""
}

variable "s3_enabled" {
  description = "Set S3_ENABLED=true in the app so scraped files are uploaded to the bucket."
  type        = bool
  default     = true
}

variable "create_dynamodb_table" {
  description = "Create the DynamoDB table backing the shared visited-URL store (used by Lambda/cloud runs)."
  type        = bool
  default     = true
}

variable "dynamodb_table_name" {
  description = "DynamoDB table name for the visited store."
  type        = string
  default     = "webscraper-visited"
}

########################################
# Lambda (optional — the scraper backend the web app invokes)
########################################

variable "enable_lambda" {
  description = "Provision the scraper Lambda + its ECR repository. See README for the image build/push step."
  type        = bool
  default     = false
}

variable "lambda_function_name" {
  description = "Name of the scraper Lambda function the web app invokes."
  type        = string
  default     = "webscraper"
}

variable "lambda_image_uri" {
  description = <<-EOT
    Full ECR image URI (repo:tag or repo@digest) for the scraper Lambda.
    The function resource is only created once this is non-empty, because the
    container image must be built and pushed before Lambda can reference it.
  EOT
  type        = string
  default     = ""
}

variable "lambda_timeout" {
  description = "Lambda timeout in seconds (document-heavy pages need several minutes)."
  type        = number
  default     = 600
}

variable "lambda_memory_mb" {
  description = "Lambda memory in MB."
  type        = number
  default     = 1024
}
