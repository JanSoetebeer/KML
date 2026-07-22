########################################
# DynamoDB table — shared visited-URL store (dedup / loop guard)
########################################
#
# Matches webscraper/state/visited_store.py: a single string hash key holding
# the normalised URL. On-demand billing keeps it free-tier friendly.

resource "aws_dynamodb_table" "visited" {
  count        = var.create_dynamodb_table ? 1 : 0
  name         = var.dynamodb_table_name
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "url"

  attribute {
    name = "url"
    type = "S"
  }

  tags = {
    Name = var.dynamodb_table_name
  }
}
