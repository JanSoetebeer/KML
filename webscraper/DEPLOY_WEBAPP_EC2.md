# Deploying the admin web app to AWS EC2 (Elastic IP + self-signed HTTPS)

Step-by-step guide to host the FastAPI admin frontend on a single EC2 instance,
reachable publicly at a fixed **Elastic IP**, gated by login, and encrypted with
a **self-signed** certificate (no domain required). The app triggers the scraper
by invoking the deployed Lambda function.

```
Browser ──HTTPS (self-signed)──► Caddy :443 ──► webapp :8000 (FastAPI)
                                                    │
                                                    └── boto3 lambda:InvokeFunction ──► Lambda (scraper)
```

Prerequisites: the scraper Lambda is already deployed (see `DEPLOY_AWS.md`). AWS
CLI configured locally, and an SSH key pair.

> **Security note.** The certificate is self-signed, so browsers show a
> "not secure / proceed anyway" warning — the traffic is still encrypted.
> Passwords are stored as bcrypt hashes; session tokens are signed and expire.
> Keep the SSH port (22) restricted to your own IP.

---

## Step 0 — Shared variables (local PowerShell)

```powershell
$REGION  = "eu-central-1"
$ACCOUNT = (aws sts get-caller-identity --query Account --output text)
$FUNC    = "webscraper"                       # Lambda function name
$EC2ROLE = "webscraper-webapp-role"           # IAM role for the EC2 instance
$SG      = "webscraper-webapp-sg"             # security group name
$KEY     = "webscraper-key"                   # EC2 key pair name
$ACCOUNT
```

---

## Step 1 — IAM instance role (invoke Lambda, no static keys)

The web app calls Lambda via boto3. Give the instance a role instead of baking
in AWS keys.

```powershell
# Trust policy lets EC2 assume the role (file provided: aws/ec2-trust-policy.json)
aws iam create-role --role-name $EC2ROLE `
  --assume-role-policy-document file://aws/ec2-trust-policy.json

# Permission to invoke the scraper Lambda.
# Edit aws/webapp-invoke-lambda-policy.json first: replace ACCOUNT_ID (and the
# region/function name if you changed them).
aws iam put-role-policy --role-name $EC2ROLE `
  --policy-name invoke-scraper-lambda `
  --policy-document file://aws/webapp-invoke-lambda-policy.json

# Instance profile wrapping the role (EC2 attaches profiles, not roles directly).
aws iam create-instance-profile --instance-profile-name $EC2ROLE
aws iam add-role-to-instance-profile --instance-profile-name $EC2ROLE --role-name $EC2ROLE
```

---

## Step 2 — Security group (ports 22 / 80 / 443)

```powershell
$MYIP = (Invoke-RestMethod https://checkip.amazonaws.com).Trim()
$VPC  = (aws ec2 describe-vpcs --filters "Name=isDefault,Values=true" --query "Vpcs[0].VpcId" --output text --region $REGION)

$SGID = (aws ec2 create-security-group --group-name $SG `
  --description "webscraper admin webapp" --vpc-id $VPC `
  --query GroupId --output text --region $REGION)

# SSH only from your current IP
aws ec2 authorize-security-group-ingress --group-id $SGID `
  --protocol tcp --port 22 --cidr "$MYIP/32" --region $REGION
# HTTP (redirects to HTTPS) + HTTPS from anywhere
aws ec2 authorize-security-group-ingress --group-id $SGID --protocol tcp --port 80  --cidr 0.0.0.0/0 --region $REGION
aws ec2 authorize-security-group-ingress --group-id $SGID --protocol tcp --port 443 --cidr 0.0.0.0/0 --region $REGION
```

---

## Step 3 — Launch the instance

```powershell
# Key pair (saves a .pem you use for SSH).
# NOTE: use Out-File -Encoding ascii — the plain `>` redirect writes UTF-16 and
# produces an "invalid format" error from ssh.
aws ec2 create-key-pair --key-name $KEY --query KeyMaterial --output text --region $REGION |
  Out-File -Encoding ascii "$KEY.pem"

# Latest Amazon Linux 2023 AMI
$AMI = (aws ssm get-parameters --names /aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64 `
  --query "Parameters[0].Value" --output text --region $REGION)

$INSTANCE = (aws ec2 run-instances --image-id $AMI --instance-type t3.small `
  --key-name $KEY --security-group-ids $SGID `
  --iam-instance-profile Name=$EC2ROLE `
  --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=webscraper-webapp}]" `
  --query "Instances[0].InstanceId" --output text --region $REGION)
$INSTANCE
```

`t3.small` (2 GB RAM) is a sensible minimum for Docker + Caddy + uvicorn.

---

## Step 4 — Elastic IP (fixed public address)

```powershell
$ALLOC = (aws ec2 allocate-address --domain vpc --query AllocationId --output text --region $REGION)
aws ec2 associate-address --instance-id $INSTANCE --allocation-id $ALLOC --region $REGION

$PUBIP = (aws ec2 describe-addresses --allocation-ids $ALLOC --query "Addresses[0].PublicIp" --output text --region $REGION)
"App will be at: https://$PUBIP"
```

---

## Step 5 — Install Docker on the instance

SSH in (`ec2-user` is the default AL2023 login):

```powershell
ssh -i "$KEY.pem" ec2-user@$PUBIP
```

Then on the instance:

```bash
sudo dnf update -y
sudo dnf install -y docker git
sudo systemctl enable --now docker
sudo usermod -aG docker ec2-user
# Compose v2 plugin
sudo mkdir -p /usr/local/lib/docker/cli-plugins
sudo curl -SL "https://github.com/docker/compose/releases/latest/download/docker-compose-linux-x86_64" \
  -o /usr/local/lib/docker/cli-plugins/docker-compose
sudo chmod +x /usr/local/lib/docker/cli-plugins/docker-compose
# buildx plugin (compose build needs buildx >= 0.17; AL2023's docker pkg lacks it)
BUILDX_VER=v0.19.3
sudo curl -SL "https://github.com/docker/buildx/releases/download/${BUILDX_VER}/buildx-${BUILDX_VER}.linux-amd64" \
  -o /usr/local/lib/docker/cli-plugins/docker-buildx
sudo chmod +x /usr/local/lib/docker/cli-plugins/docker-buildx
exit   # re-login so the docker group applies
```

Log back in and verify: `docker compose version`.

---

## Step 6 — Get the code onto the instance

Either clone your repo, or copy from your machine:

```bash
# Option A — git
git clone <your-repo-url> ~/KML
cd ~/KML/webscraper
```

```powershell
# Option B — from your local machine (scp the webscraper folder)
scp -i "$KEY.pem" -r .\webscraper ec2-user@${PUBIP}:~/webscraper
```

---

## Step 7 — Configure `.env`

In the `webscraper` folder on the instance, create `.env` (copy from
`.env.example`) and set at least:

```bash
cp .env.example .env
# Generate a strong signing key:
python3 -c "import secrets; print('SECRET_KEY=' + secrets.token_urlsafe(48))"
```

Edit `.env` and set:

- `SITE_ADDRESS=` your Elastic IP (e.g. `63.183.184.19`) — required so Caddy can
  provision the self-signed certificate for that address
- `SECRET_KEY=` the generated value (required — the app won't sign tokens without it)
- `ADMIN_USERNAME=` your chosen admin login (applied only on first DB creation)
- `ADMIN_PASSWORD=` a strong admin password (applied only on first DB creation)
- `LAMBDA_FUNCTION_NAME=webscraper` (the deployed scraper function)
- `AWS_REGION=eu-central-1`

Leave `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` **empty** — the instance role
supplies credentials automatically.

---

## Step 8 — Launch the stack

```bash
docker compose up -d --build
docker compose ps
docker compose logs -f webapp   # Ctrl-C to stop tailing
```

Open **`https://<ELASTIC_IP>`** in a browser, accept the self-signed warning,
and log in with the admin credentials from `.env`.

First things to do in the UI:
1. **Change the admin password** (Benutzerverwaltung → Passwort ändern).
2. Create accounts for your project partners.

---

## Step 9 — Redeploy the scraper (ship the `file_types` feature)

The web app calls the Lambda, so the Lambda image must be up to date. From your
local machine, rebuild + push and update the function (full detail in
`DEPLOY_AWS.md`, Steps 4–6):

```powershell
$IMAGE = "$ACCOUNT.dkr.ecr.$REGION.amazonaws.com/webscraper:latest"
aws ecr get-login-password --region $REGION | docker login --username AWS --password-stdin "$ACCOUNT.dkr.ecr.$REGION.amazonaws.com"
docker build -t $IMAGE .
docker push $IMAGE
aws lambda update-function-code --function-name $FUNC --image-uri $IMAGE --region $REGION
```

---

## Updating the web app later

```bash
cd ~/webscraper        # (or ~/KML/webscraper)
git pull               # or re-scp the changed files
docker compose up -d --build
```

Persistent data (`app.db`, uploaded models, `Log.txt`) lives in the
`webapp_data` Docker volume and survives rebuilds. To inspect it:

```bash
docker compose exec webapp ls -la /data
```

---

## Teardown (avoid charges)

```powershell
aws ec2 terminate-instances --instance-ids $INSTANCE --region $REGION
aws ec2 release-address --allocation-id $ALLOC --region $REGION
aws ec2 delete-security-group --group-id $SGID --region $REGION
aws iam remove-role-from-instance-profile --instance-profile-name $EC2ROLE --role-name $EC2ROLE
aws iam delete-instance-profile --instance-profile-name $EC2ROLE
aws iam delete-role-policy --role-name $EC2ROLE --policy-name invoke-scraper-lambda
aws iam delete-role --role-name $EC2ROLE
```
