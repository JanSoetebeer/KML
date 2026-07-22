output "webapp_public_ip" {
  description = "Elastic IP of the web app instance."
  value       = aws_eip.webapp.public_ip
}

output "webapp_url" {
  description = "HTTPS URL of the admin web app (self-signed cert — expect a browser warning)."
  value       = "https://${aws_eip.webapp.public_ip}"
}

output "ssh_command" {
  description = "Convenience SSH command (needs the private key matching ssh_public_key)."
  value       = "ssh ec2-user@${aws_eip.webapp.public_ip}"
}

output "instance_id" {
  description = "EC2 instance ID."
  value       = aws_instance.webapp.id
}

output "s3_bucket" {
  description = "Scraped-output S3 bucket name."
  value       = local.bucket_name
}

output "dynamodb_table" {
  description = "Visited-store DynamoDB table name (empty if not created)."
  value       = var.create_dynamodb_table ? var.dynamodb_table_name : ""
}

output "ecr_repository_url" {
  description = "ECR repository URL for the scraper image (empty unless enable_lambda=true)."
  value       = var.enable_lambda ? aws_ecr_repository.scraper[0].repository_url : ""
}

output "lambda_function_name" {
  description = "Scraper Lambda function name (created only once lambda_image_uri is set)."
  value       = local.create_lambda_fn ? aws_lambda_function.scraper[0].function_name : ""
}
