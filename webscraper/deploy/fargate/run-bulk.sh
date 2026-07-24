#!/usr/bin/env bash
# Launch a bulk crawl on Fargate from your own machine (alternative to the
# bulk-crawl.yml GitHub Actions workflow). Requires the AWS CLI configured with
# permission to ecs:RunTask + iam:PassRole (see webscraper/DEPLOY_BULK_FARGATE.md).
#
# Usage:
#   deploy/fargate/run-bulk.sh s3://webscraper-output-<acct>/lists/unis.csv [profile] [max_jobs]
#
# Env overrides: AWS_REGION (default eu-central-1), FARGATE_SUBNETS (comma-sep),
# FARGATE_SECURITY_GROUP (required — an egress-enabled SG in the default VPC).
set -euo pipefail

URLS_S3="${1:?Usage: run-bulk.sh <s3://.../list.csv> [profile] [max_jobs]}"
PROFILE="${2:-modulhandbuch}"
MAX_JOBS="${3:-8}"

REGION="${AWS_REGION:-eu-central-1}"
CLUSTER="webscraper-bulk"
FAMILY="webscraper-bulk"

SG="${FARGATE_SECURITY_GROUP:?Set FARGATE_SECURITY_GROUP to an egress-enabled SG id}"
SUBNETS="${FARGATE_SUBNETS:-}"
if [ -z "$SUBNETS" ]; then
  VPC=$(aws ec2 describe-vpcs --filters Name=isDefault,Values=true \
    --query "Vpcs[0].VpcId" --output text --region "$REGION")
  SUBNETS=$(aws ec2 describe-subnets --filters Name=vpc-id,Values=$VPC \
    --query "Subnets[].SubnetId" --output text --region "$REGION" | tr '\t' ',')
fi

BATCH_ID=$(python -c "import uuid;print(uuid.uuid4().hex)" 2>/dev/null || uuidgen | tr -d '-')

cat > /tmp/bulk-overrides.json <<JSON
{
  "containerOverrides": [
    {
      "name": "webscraper-bulk",
      "environment": [
        { "name": "BULK_URLS_S3",  "value": "$URLS_S3" },
        { "name": "BULK_BATCH_ID", "value": "$BATCH_ID" },
        { "name": "CRAWL_PROFILE", "value": "$PROFILE" },
        { "name": "BULK_MAX_JOBS", "value": "$MAX_JOBS" },
        { "name": "MAX_CONCURRENT_JOBS", "value": "$MAX_JOBS" }
      ]
    }
  ]
}
JSON

ARN=$(aws ecs run-task \
  --cluster "$CLUSTER" \
  --task-definition "$FAMILY" \
  --launch-type FARGATE \
  --count 1 \
  --network-configuration "awsvpcConfiguration={subnets=[$SUBNETS],securityGroups=[$SG],assignPublicIp=ENABLED}" \
  --overrides file:///tmp/bulk-overrides.json \
  --started-by "cli-$(whoami)" \
  --query "tasks[0].taskArn" --output text --region "$REGION")

echo "Launched: $ARN"
echo "Batch id: $BATCH_ID  →  s3://webscraper-output-<account>/manifests/$BATCH_ID.jsonl"
echo "Logs:     aws logs tail /ecs/webscraper-bulk --follow --region $REGION"
