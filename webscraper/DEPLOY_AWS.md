# Deploying the webscraper to AWS Lambda

Step-by-step guide to move the scraper from local execution to AWS Lambda, with
results saved to an S3 bucket. Follow the steps in order. Commands are written
for **PowerShell**; notes mark anything OS-specific.

> Why a container image (not a ZIP)? Scrapy pulls in compiled libraries
> (`lxml`, `Twisted`, `cryptography`). A container image bundles them reliably,
> whereas a ZIP requires fiddly manylinux builds. The provided `Dockerfile`
> handles everything.

---

## Prerequisites

Install and verify these once:

1. **AWS CLI v2** — https://aws.amazon.com/cli/
   ```powershell
   aws --version
   aws configure          # enter your Access Key, Secret, region (eu-central-1)
   ```
2. **Docker Desktop** (running) — https://www.docker.com/products/docker-desktop/
   ```powershell
   docker --version
   ```
3. Confirm your identity / account ID:
   ```powershell
   aws sts get-caller-identity
   ```

---

## Step 0 — Set shared variables

Run this block once per PowerShell session. Adjust names as you like (bucket
names must be globally unique).

```powershell
$REGION   = "eu-central-1"
$ACCOUNT  = (aws sts get-caller-identity --query Account --output text)
$BUCKET   = "webscraper-output-$ACCOUNT"        # globally-unique S3 bucket
$REPO     = "webscraper"                          # ECR repository name
$FUNC     = "webscraper"                          # Lambda function name
$ROLE     = "webscraper-lambda-role"              # IAM execution role name
$TABLE    = "webscraper-visited"                  # DynamoDB visited-URL table
$IMAGE    = "$ACCOUNT.dkr.ecr.$REGION.amazonaws.com/${REPO}:latest"

# sanity check
$ACCOUNT; $BUCKET; $IMAGE
```

---

## Step 1 — Create the S3 output bucket

```powershell
aws s3api create-bucket `
  --bucket $BUCKET `
  --region $REGION `
  --create-bucket-configuration LocationConstraint=$REGION

# Block all public access (recommended)
aws s3api put-public-access-block `
  --bucket $BUCKET `
  --public-access-block-configuration BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
```

> Note: for `us-east-1` only, omit the `--create-bucket-configuration` flag.

---

## Step 2 — Create the Lambda execution IAM role

The role lets Lambda write logs and access **only** your bucket. Credentials
are obtained from this role at runtime — you never put keys in the image.

```powershell
# 2a. Create the role with the Lambda trust policy (file provided in aws/)
aws iam create-role `
  --role-name $ROLE `
  --assume-role-policy-document file://aws/trust-policy.json

# 2b. Attach the AWS-managed basic logging policy (CloudWatch Logs)
aws iam attach-role-policy `
  --role-name $ROLE `
  --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole

# 2c. Create an inline S3 policy scoped to your bucket.
#     First substitute the bucket name into the template:
(Get-Content aws/s3-policy.json) -replace "REPLACE_WITH_BUCKET_NAME", $BUCKET | Set-Content aws/s3-policy.resolved.json

aws iam put-role-policy `
  --role-name $ROLE `
  --policy-name webscraper-s3-access `
  --policy-document file://aws/s3-policy.resolved.json

# 2d. Capture the role ARN for later
$ROLE_ARN = (aws iam get-role --role-name $ROLE --query Role.Arn --output text)
$ROLE_ARN
```

> IAM role propagation can take ~10 seconds. If Step 5 fails with an
> "cannot be assumed" error, wait and retry.

---

## Step 2b — Create the DynamoDB visited-URL table

This is the shared dedup store so re-running never re-scrapes the same URL and
crawls can't loop — replacing the local `state/visited.json` that doesn't work
across Lambda invocations.

```powershell
# Create an on-demand (pay-per-request) table keyed by the normalised URL.
aws dynamodb create-table `
  --table-name $TABLE `
  --attribute-definitions AttributeName=url,AttributeType=S `
  --key-schema AttributeName=url,KeyType=HASH `
  --billing-mode PAY_PER_REQUEST `
  --region $REGION

# Wait until the table is ACTIVE before continuing
aws dynamodb wait table-exists --table-name $TABLE --region $REGION
```

Grant the Lambda role read/write access to it (the policy file is in `aws/`):

```powershell
# The template targets the default table name; substitute yours if you changed $TABLE
(Get-Content aws/dynamodb-policy.json) -replace "webscraper-visited", $TABLE | Set-Content aws/dynamodb-policy.resolved.json

aws iam put-role-policy `
  --role-name $ROLE `
  --policy-name webscraper-dynamodb-access `
  --policy-document file://aws/dynamodb-policy.resolved.json
```

> The `url` attribute is the table's partition key; it stores the normalised
> URL (lower-cased host, no fragment, no trailing slash) so the same page is
> never recorded twice.

---

## Step 3 — Create an ECR repository (image registry)

```powershell
aws ecr create-repository --repository-name $REPO --region $REGION
```

---

## Step 4 — Build and push the container image

```powershell
# 4a. Authenticate Docker to your ECR registry
aws ecr get-login-password --region $REGION | `
  docker login --username AWS --password-stdin "$ACCOUNT.dkr.ecr.$REGION.amazonaws.com"

# 4b. Build the image for the Lambda runtime architecture (x86_64).
#     Run this from the project directory (where the Dockerfile lives):
cd "C:\Users\jan\FH Wedel\Master\SS26\ML\KML\webscraper"
docker build --platform linux/amd64 -t "${REPO}:latest" .

# 4c. Tag and push to ECR
docker tag "${REPO}:latest" $IMAGE
docker push $IMAGE
```

---

## Step 5 — Create the Lambda function

```powershell
aws lambda create-function `
  --function-name $FUNC `
  --package-type Image `
  --code ImageUri=$IMAGE `
  --role $ROLE_ARN `
  --timeout 300 `
  --memory-size 512 `
  --region $REGION `
  --environment "Variables={S3_ENABLED=true,S3_BUCKET=$BUCKET,LOCAL_ENABLED=false,LOG_DIR=/tmp/logs,VISITED_STORE_BACKEND=dynamodb,DYNAMODB_TABLE=$TABLE,LOG_LEVEL=INFO}"
```

Why these env vars:

| Variable | Value | Reason |
|---|---|---|
| `S3_ENABLED` | `true` | Turn on the S3 upload pipeline |
| `S3_BUCKET` | your bucket | Where documents are stored |
| `LOCAL_ENABLED` | `false` | Lambda's project dir is **read-only** |
| `LOG_DIR` | `/tmp/logs` | Only `/tmp` is writable on Lambda |
| `VISITED_STORE_BACKEND` | `dynamodb` | Shared dedup store across invocations |
| `DYNAMODB_TABLE` | `$TABLE` | The visited-URL table (created in Step 2b) |

---

## Step 6 — Test it

```powershell
# Single URL
aws lambda invoke `
  --function-name $FUNC `
  --region $REGION `
  --cli-binary-format raw-in-base64-out `
  --payload '{\"url\": \"https://www.tum.de/studium/studienangebot/detail/informatik-bachelor-of-science-bsc\"}' `
  response.json

Get-Content response.json
```

Then confirm the documents landed in S3:

```powershell
aws s3 ls "s3://$BUCKET/scraped/" --recursive
```

View logs:

```powershell
aws logs tail "/aws/lambda/$FUNC" --since 10m --region $REGION --follow
```

Multiple URLs in one invocation:

```powershell
aws lambda invoke --function-name $FUNC --region $REGION `
  --cli-binary-format raw-in-base64-out `
  --payload '{\"urls\": [\"https://www.w3.org/TR/\", \"https://example.com\"], \"max_jobs\": 2}' `
  response.json
```

---

## Step 7 — Updating after code changes

Rebuild, push, and tell Lambda to pull the new image:

```powershell
docker build --platform linux/amd64 -t "${REPO}:latest" .
docker tag "${REPO}:latest" $IMAGE
docker push $IMAGE

aws lambda update-function-code `
  --function-name $FUNC `
  --image-uri $IMAGE `
  --region $REGION
```

To change env vars later:

```powershell
aws lambda update-function-configuration `
  --function-name $FUNC `
  --environment "Variables={S3_ENABLED=true,S3_BUCKET=$BUCKET,LOCAL_ENABLED=false,LOG_DIR=/tmp/logs,VISITED_STORE_BACKEND=dynamodb,DYNAMODB_TABLE=$TABLE,LOG_LEVEL=DEBUG}" `
  --region $REGION
```

---

## Step 8 — (Optional) Add triggers

Pick whichever fits your workflow.

### a) Scheduled runs (EventBridge)
```powershell
aws events put-rule --name webscraper-daily --schedule-expression "rate(1 day)" --region $REGION
# Then add the Lambda as a target and grant events:InvokeFunction permission.
```

### b) Queue-driven (SQS)
Create an SQS queue, then add it as an event source. The handler already parses
SQS `Records` (each message body is `{"url": "..."}`).
```powershell
aws lambda create-event-source-mapping `
  --function-name $FUNC `
  --event-source-arn <your-queue-arn> `
  --batch-size 5 --region $REGION
```

### c) HTTP endpoint (Function URL)
```powershell
aws lambda create-function-url-config --function-name $FUNC --auth-type AWS_IAM --region $REGION
# POST {"url": "..."} to the returned URL.
```

---

## Important caveats (read before relying on this in production)

1. **Dedup uses DynamoDB on Lambda.** With `VISITED_STORE_BACKEND=dynamodb` the
   visited store is shared across all invocations, so re-runs skip already-
   scraped URLs and crawls can't loop. Locally you can keep the default
   `json` backend (`state/visited.json`) — no AWS needed.
2. **One invocation = one fresh subprocess.** This is intentional (Twisted's
   reactor can't restart). It adds ~1–2s cold-start overhead per call.
3. **robots.txt is still honoured** (`ROBOTSTXT_OBEY=true`). Sites that
   disallow crawling will return zero documents — that's expected/ethical.
4. **Large documents + memory.** Files are buffered in memory before upload.
   Raise `--memory-size` if you scrape large PDFs.

---

## Teardown (avoid charges)

```powershell
aws lambda delete-function --function-name $FUNC --region $REGION
aws ecr delete-repository --repository-name $REPO --force --region $REGION
aws iam delete-role-policy --role-name $ROLE --policy-name webscraper-s3-access
aws iam delete-role-policy --role-name $ROLE --policy-name webscraper-dynamodb-access
aws iam detach-role-policy --role-name $ROLE --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole
aws iam delete-role --role-name $ROLE
aws dynamodb delete-table --table-name $TABLE --region $REGION
aws s3 rb "s3://$BUCKET" --force
```
