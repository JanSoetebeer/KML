terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.40"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }

  # Optional: keep state in S3 instead of a local file. Fill in and uncomment,
  # then run `terraform init -migrate-state`.
  #
  # backend "s3" {
  #   bucket = "your-tfstate-bucket"
  #   key    = "webscraper/terraform.tfstate"
  #   region = "eu-central-1"
  # }
}
