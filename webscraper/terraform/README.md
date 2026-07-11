# Terraform — webscraper infrastructure

Provisions the webscraper stack on AWS as code, replacing the manual click-ops
in [`DEPLOY_WEBAPP_EC2.md`](../DEPLOY_WEBAPP_EC2.md) and
[`DEPLOY_AWS.md`](../DEPLOY_AWS.md).

## What it creates

| Resource | File | Notes |
|---|---|---|
| EC2 instance (Amazon Linux 2023) | `ec2.tf` | Runs the FastAPI web app via Docker Compose + Caddy; bootstrapped by `user_data.sh.tftpl` |
| Elastic IP | `ec2.tf` | Fixed public address; injected into the app as `SITE_ADDRESS` |
| Security group | `network.tf` | SSH from your IP only; HTTP/HTTPS from the internet |
| IAM instance role | `iam.tf` | Lets the instance invoke the scraper Lambda + use S3 / DynamoDB — no static keys |
| S3 bucket | `s3.tf` | Stores scraped files (private, encrypted) |
| DynamoDB table | `dynamodb.tf` | Shared visited-URL store (dedup / loop guard) |
| ECR repo + Lambda | `lambda.tf` | **Optional** (`enable_lambda=true`) — the scraper backend |

```
Browser ──HTTPS──► Caddy :443 ──► webapp :8000 (FastAPI, EC2)
                                      │ boto3 lambda:InvokeFunction
                                      ▼
                                  Lambda (scraper) ──► S3 + DynamoDB
```

## Prerequisites

- Terraform >= 1.5 and the AWS CLI configured (`aws configure`) with credentials
  that can create the resources above.
- An SSH key pair — provide the **public** key via `ssh_public_key`.

## Deploy the web app (no Lambda)

```bash
cd webscraper/terraform
cp terraform.tfvars.example terraform.tfvars   # then edit it
export TF_VAR_admin_password='a-strong-password'

terraform init
terraform plan
terraform apply
```

`terraform output webapp_url` prints the HTTPS address. The certificate is
self-signed, so the browser shows a "not secure / proceed anyway" warning — the
traffic is still encrypted. First boot takes a few minutes while the instance
installs Docker and builds the image; watch progress with:

```bash
ssh ec2-user@$(terraform output -raw webapp_public_ip)
sudo tail -f /var/log/cloud-init-output.log
cd /opt/app/repo/webscraper && docker compose ps
```

> Without a Lambda the web app has no scraper backend to invoke, so scrape runs
> report an error. Add the Lambda (below) or run the app on a full checkout
> where the local-subprocess fallback works.

## Add the scraper Lambda (optional)

The Lambda runs from a container image, which must exist in ECR before the
function can reference it — so it's a three-step flow:

```bash
# 1. Create the ECR repository.
terraform apply -var="enable_lambda=true"
REPO=$(terraform output -raw ecr_repository_url)
REGION=eu-central-1   # your configured aws_region

# 2. Build & push the image (from webscraper/, which holds the Lambda Dockerfile).
cd ..
aws ecr get-login-password --region "$REGION" \
  | docker login --username AWS --password-stdin "${REPO%/*}"
docker build -t "$REPO:latest" .
docker push "$REPO:latest"

# 3. Create the function pointing at the pushed image.
cd terraform
terraform apply -var="enable_lambda=true" -var="lambda_image_uri=$REPO:latest"
```

Set `enable_lambda = true` (and `lambda_image_uri`) in `terraform.tfvars` to make
these permanent instead of passing `-var` each time.

## Updating the app

- **Code changes:** SSH in and `cd /opt/app/repo/webscraper && git pull && docker compose up -d --build`, or taint the instance (`terraform apply -replace=aws_instance.webapp`) to re-bootstrap from scratch.
- **Lambda image:** push a new tag and `terraform apply` with the new `lambda_image_uri`.

## Notes & caveats

- **State contains secrets.** `random_password.secret_key` and `admin_password`
  live in `terraform.tfstate`. Keep state private — use the S3 backend stub in
  `versions.tf` for team use, and never commit `*.tfstate` / `*.tfvars` (see
  `.gitignore`).
- Uses the account's **default VPC** and its first subnet, matching the manual
  guide. Point at a custom network by replacing the `data` sources in `main.tf`.
- `terraform destroy` removes everything, including the S3 bucket
  (`force_delete` is not set on the bucket, so empty it first if it has objects)
  and the ECR repo (`force_delete = true`).
