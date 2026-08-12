<#
=====================================================================
 aws_bootstrap.ps1 - one-shot, idempotent rebuild of the ENTIRE
 webscraper AWS stack in a fresh account/sandbox.
=====================================================================

 Why this exists
 ---------------
 The AWS sandbox lease expires periodically and takes every resource
 (S3, DynamoDB, Lambda, EC2, IAM, ECS) with it. This script recreates
 the whole stack from the policy templates in webscraper/aws/ using the
 CURRENT account id (resolved dynamically), so a rebuild is one command.

 It is the scripted equivalent of, and supersedes, the manual click-ops
 in DEPLOY_AWS.md + DEPLOY_WEBAPP_EC2.md + DEPLOY_CICD.md +
 DEPLOY_BULK_FARGATE.md. Every step is idempotent: re-running skips what
 already exists and only fills gaps.

 What it creates
 ---------------
   Phase 1  S3 bucket (private, encrypted)           [core]
   Phase 2  DynamoDB visited-URL table               [core]
   Phase 3  ECR repository                            [core]
   Phase 4  Lambda execution role + policies          [core]
   Phase 5  Build + push the container image          [core]
   Phase 6  Lambda function (interactive scraper)      [core]
   Phase 7  EC2 webapp IAM role + instance profile     [webapp]
   Phase 8  EC2 security group + SSH key pair          [webapp]
   Phase 9  EC2 instance + Elastic IP (self-bootstraps)[webapp]
   Phase 10 GitHub OIDC provider + deploy role         [cicd]
   Phase 11 Fargate: cluster, roles, SG, task def      [bulk]
   Phase 12 Summary + the GitHub variables to set

 Prerequisites (you confirmed these are ready)
 ---------------------------------------------
   * AWS CLI v2 configured for the NEW sandbox
       aws sts get-caller-identity   # must succeed
   * Docker Desktop running (for Phase 5 image build)

 Usage
 -----
   # from the repo root:
   pwsh webscraper/deploy/aws_bootstrap.ps1
   # or skip parts you don't want this run:
   pwsh webscraper/deploy/aws_bootstrap.ps1 -SkipImage -SkipEc2

 Params let you re-run cheaply (e.g. -SkipImage once the image is pushed).
#>

[CmdletBinding()]
param(
  [string] $Region        = "eu-central-1",
  [string] $Project       = "webscraper",
  [string] $RepoUrl       = "https://github.com/JanSoetebeer/KML.git",
  [string] $RepoBranch    = "main",
  [string] $InstanceType  = "t3.small",
  [string] $AdminUsername = "admin",
  # Seed admin password (applied only on first DB creation). If empty a strong
  # random one is generated and printed at the end.
  [string] $AdminPassword = "",
  [switch] $SkipImage,     # skip Phase 5 (Docker build/push) - image already in ECR
  [switch] $SkipEc2,       # skip Phases 7-9 (EC2 webapp)
  [switch] $SkipCicd,      # skip Phase 10 (GitHub OIDC deploy role)
  [switch] $SkipFargate    # skip Phase 11 (Fargate bulk)
)

$ErrorActionPreference = "Stop"

# --- Resolve repo layout (this file lives in <repo>/webscraper/deploy/) -------
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot  = (Resolve-Path (Join-Path $ScriptDir "..\..")).Path
$AwsDir    = Join-Path $RepoRoot "webscraper\aws"
$Dockerfile = "webscraper/Dockerfile"

# --- Names (match the deploy docs + CI/CD workflows exactly) ------------------
$Table       = "$Project-visited"
$EcrRepo     = $Project
$LambdaFn    = $Project
$LambdaRole  = "$Project-lambda-role"
$WebappRole  = "$Project-webapp-role"
$WebappSg    = "$Project-webapp-sg"
$KeyName     = "$Project-key"
$InstanceTag = "$Project-webapp"
$DeployRole  = "github-actions-deploy"
$BulkExec    = "$Project-bulk-exec"
$BulkTask    = "$Project-bulk-task"
$BulkCluster = "$Project-bulk"
$BulkFamily  = "$Project-bulk"
$BulkSg      = "$Project-bulk-sg"
$BulkLogGroup = "/ecs/$Project-bulk"

# ============================================================================
# Helpers
# ============================================================================
function Say  ($m) { Write-Host "  $m" -ForegroundColor Gray }
function Ok   ($m) { Write-Host "  [ok] $m" -ForegroundColor Green }
function Skip ($m) { Write-Host "  [skip] $m" -ForegroundColor DarkYellow }
function Head ($m) { Write-Host "`n=== $m ===" -ForegroundColor Cyan }
function Die  ($m) { Write-Host "`n[FATAL] $m" -ForegroundColor Red; exit 1 }

# Run an AWS CLI query that is expected to sometimes fail (existence probe).
# Returns $true if exit code 0. Never throws.
function Test-Aws {
  param([Parameter(ValueFromRemainingArguments=$true)] $CliArgs)
  $ErrorActionPreference = "Continue"
  & aws @CliArgs 2>$null | Out-Null
  $rc = $LASTEXITCODE
  $ErrorActionPreference = "Stop"
  return ($rc -eq 0)
}

# Render a webscraper/aws/<name> template to <RepoRoot>/<out> with ACCOUNT_ID /
# REGION substituted. Uses -creplace (case-SENSITIVE) so the lowercase
# "awslogs-region" key in the task def is never touched. ASCII, no BOM - the
# AWS CLI rejects non-ASCII / UTF-16 policy files.
function Resolve-Template {
  param([string]$Name, [string]$OutFile)
  $src = Join-Path $AwsDir $Name
  $dst = Join-Path $RepoRoot $OutFile
  (Get-Content $src -Raw) -creplace 'ACCOUNT_ID', $Account -creplace 'REGION', $Region |
    Set-Content $dst -Encoding ascii -NoNewline
  return $dst
}

function New-UrlSafeSecret {
  param([int]$Bytes = 48)
  $buf = New-Object 'System.Byte[]' $Bytes
  [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($buf)
  return ([Convert]::ToBase64String($buf)) -replace '\+','-' -replace '/','_' -replace '=',''
}

# ============================================================================
# Phase 0 - preflight
# ============================================================================
Head "Phase 0 - preflight"
if (-not (Test-Aws sts get-caller-identity --region $Region)) {
  Die "aws sts get-caller-identity failed. Run 'aws configure' with the new sandbox credentials first."
}
$Account = (aws sts get-caller-identity --query Account --output text).Trim()
$Bucket  = "$Project-output-$Account"
$Image   = "$Account.dkr.ecr.$Region.amazonaws.com/${EcrRepo}:latest"
Ok "Account = $Account   Region = $Region"
Ok "Bucket  = $Bucket"
Ok "Image   = $Image"

if (-not $SkipImage) {
  $ErrorActionPreference = "Continue"; docker info 2>$null | Out-Null; $dok = ($LASTEXITCODE -eq 0); $ErrorActionPreference = "Stop"
  if (-not $dok) { Die "Docker is not running (needed for Phase 5). Start Docker Desktop, or pass -SkipImage." }
  Ok "Docker is running"
}

# ============================================================================
# Phase 1 - S3 bucket
# ============================================================================
Head "Phase 1 - S3 bucket"
if (Test-Aws s3api head-bucket --bucket $Bucket) {
  Skip "bucket $Bucket already exists"
} else {
  if ($Region -eq "us-east-1") {
    aws s3api create-bucket --bucket $Bucket --region $Region | Out-Null
  } else {
    aws s3api create-bucket --bucket $Bucket --region $Region `
      --create-bucket-configuration "LocationConstraint=$Region" | Out-Null
  }
  Ok "created bucket $Bucket"
}
aws s3api put-public-access-block --bucket $Bucket `
  --public-access-block-configuration "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true" | Out-Null
# New S3 buckets are SSE-S3 (AES256) encrypted by default (AWS, since Jan 2023) -
# nothing else to do.
Ok "public access blocked (default SSE-S3 encryption is automatic)"

# ============================================================================
# Phase 2 - DynamoDB visited-URL table
# ============================================================================
Head "Phase 2 - DynamoDB table"
if (Test-Aws dynamodb describe-table --table-name $Table --region $Region) {
  Skip "table $Table already exists"
} else {
  aws dynamodb create-table --table-name $Table `
    --attribute-definitions AttributeName=url,AttributeType=S `
    --key-schema AttributeName=url,KeyType=HASH `
    --billing-mode PAY_PER_REQUEST --region $Region | Out-Null
  aws dynamodb wait table-exists --table-name $Table --region $Region
  Ok "created table $Table (on-demand, key=url)"
}

# ============================================================================
# Phase 3 - ECR repository
# ============================================================================
Head "Phase 3 - ECR repository"
if (Test-Aws ecr describe-repositories --repository-names $EcrRepo --region $Region) {
  Skip "repo $EcrRepo already exists"
} else {
  aws ecr create-repository --repository-name $EcrRepo --region $Region | Out-Null
  Ok "created ECR repo $EcrRepo"
}

# ============================================================================
# Phase 4 - Lambda execution role + policies
# ============================================================================
Head "Phase 4 - Lambda role"
if (Test-Aws iam get-role --role-name $LambdaRole) {
  Skip "role $LambdaRole already exists"
} else {
  aws iam create-role --role-name $LambdaRole `
    --assume-role-policy-document "file://$AwsDir\trust-policy.json" | Out-Null
  Ok "created role $LambdaRole"
}
aws iam attach-role-policy --role-name $LambdaRole `
  --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole | Out-Null
$s3Resolved    = Resolve-Template "s3-policy.json"       "s3-policy.resolved.json"
$dynamoResolved = Resolve-Template "dynamodb-policy.json" "dynamodb-policy.resolved.json"
aws iam put-role-policy --role-name $LambdaRole --policy-name "$Project-s3-access" `
  --policy-document "file://$s3Resolved" | Out-Null
aws iam put-role-policy --role-name $LambdaRole --policy-name "$Project-dynamodb-access" `
  --policy-document "file://$dynamoResolved" | Out-Null
Ok "attached logging + S3 + DynamoDB policies"
$LambdaRoleArn = (aws iam get-role --role-name $LambdaRole --query Role.Arn --output text).Trim()

# ============================================================================
# Phase 5 - build + push the container image
# ============================================================================
Head "Phase 5 - build + push image"
if ($SkipImage) {
  Skip "-SkipImage set"
} else {
  Say "docker login to ECR ..."
  aws ecr get-login-password --region $Region |
    docker login --username AWS --password-stdin "$Account.dkr.ecr.$Region.amazonaws.com"
  Say "building $Image  (from repo root, linux/amd64 - this can take several minutes) ..."
  Push-Location $RepoRoot
  try {
    docker build --platform linux/amd64 -f $Dockerfile -t "${EcrRepo}:latest" .
    if ($LASTEXITCODE -ne 0) { Die "docker build failed" }
    docker tag "${EcrRepo}:latest" $Image
    docker push $Image
    if ($LASTEXITCODE -ne 0) { Die "docker push failed" }
  } finally { Pop-Location }
  Ok "pushed $Image"
}

# ============================================================================
# Phase 6 - Lambda function
# ============================================================================
Head "Phase 6 - Lambda function"
$lambdaEnv = "Variables={S3_ENABLED=true,S3_BUCKET=$Bucket,LOCAL_ENABLED=false,LOG_DIR=/tmp/logs,VISITED_STORE_BACKEND=dynamodb,DYNAMODB_TABLE=$Table,CLASSIFIER_ENABLED=true,REVIEW_MANIFEST_DIR=/tmp/review,LOG_LEVEL=INFO}"
if (Test-Aws lambda get-function --function-name $LambdaFn --region $Region) {
  Skip "function $LambdaFn exists - updating code + config"
  if (-not $SkipImage) {
    aws lambda update-function-code --function-name $LambdaFn --image-uri $Image --region $Region | Out-Null
    aws lambda wait function-updated --function-name $LambdaFn --region $Region
  }
  aws lambda update-function-configuration --function-name $LambdaFn `
    --timeout 600 --memory-size 1536 --environment $lambdaEnv --region $Region | Out-Null
  Ok "updated $LambdaFn"
} else {
  # New IAM roles can take a few seconds to become assumable - retry.
  $created = $false
  foreach ($try in 1..6) {
    $ErrorActionPreference = "Continue"
    aws lambda create-function --function-name $LambdaFn --package-type Image `
      --code "ImageUri=$Image" --role $LambdaRoleArn --timeout 600 --memory-size 1536 `
      --environment $lambdaEnv --region $Region 2>$null | Out-Null
    $rc = $LASTEXITCODE; $ErrorActionPreference = "Stop"
    if ($rc -eq 0) { $created = $true; break }
    Say "role not assumable yet (attempt $try/6) - waiting 10s ..."; Start-Sleep -Seconds 10
  }
  if (-not $created) { Die "lambda create-function failed (is the image pushed? was Phase 5 run?)" }
  Ok "created function $LambdaFn"
}

# ============================================================================
# Phase 7 - EC2 webapp IAM role + instance profile
# ============================================================================
if ($SkipEc2) { Head "Phases 7-9 - EC2 webapp"; Skip "-SkipEc2 set" }
else {
Head "Phase 7 - webapp IAM role"
if (Test-Aws iam get-role --role-name $WebappRole) {
  Skip "role $WebappRole already exists"
} else {
  aws iam create-role --role-name $WebappRole `
    --assume-role-policy-document "file://$AwsDir\ec2-trust-policy.json" | Out-Null
  Ok "created role $WebappRole"
}
$invokeResolved  = Resolve-Template "webapp-invoke-lambda-policy.json" "webapp-invoke-lambda.resolved.json"
$webappS3Src = Join-Path $AwsDir "webapp-s3-policy.json"
$webappS3Dst = Join-Path $RepoRoot "webapp-s3.resolved.json"
(Get-Content $webappS3Src -Raw) -creplace 'REPLACE_WITH_BUCKET_NAME', $Bucket |
  Set-Content $webappS3Dst -Encoding ascii -NoNewline
$webappEcsResolved = Resolve-Template "webapp-ecs-policy.json" "webapp-ecs.resolved.json"
aws iam put-role-policy --role-name $WebappRole --policy-name "invoke-scraper-lambda" `
  --policy-document "file://$invokeResolved" | Out-Null
aws iam put-role-policy --role-name $WebappRole --policy-name "webapp-s3" `
  --policy-document "file://$webappS3Dst" | Out-Null
aws iam put-role-policy --role-name $WebappRole --policy-name "webapp-ecs" `
  --policy-document "file://$webappEcsResolved" | Out-Null
aws iam attach-role-policy --role-name $WebappRole `
  --policy-arn arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore | Out-Null
Ok "attached invoke-lambda + S3 + ECS-run + SSM policies"
if (-not (Test-Aws iam get-instance-profile --instance-profile-name $WebappRole)) {
  aws iam create-instance-profile --instance-profile-name $WebappRole | Out-Null
  aws iam add-role-to-instance-profile --instance-profile-name $WebappRole --role-name $WebappRole | Out-Null
  Ok "created instance profile $WebappRole"
} else { Skip "instance profile $WebappRole already exists" }

# ============================================================================
# Phase 8 - EC2 security group + key pair
# ============================================================================
Head "Phase 8 - webapp security group + key pair"
$Vpc = (aws ec2 describe-vpcs --filters "Name=isDefault,Values=true" `
  --query "Vpcs[0].VpcId" --output text --region $Region).Trim()
$SgId = (aws ec2 describe-security-groups --filters "Name=group-name,Values=$WebappSg" `
  "Name=vpc-id,Values=$Vpc" --query "SecurityGroups[0].GroupId" --output text --region $Region 2>$null)
if ($SgId -and $SgId -ne "None") {
  Skip "security group $WebappSg = $SgId"
} else {
  $SgId = (aws ec2 create-security-group --group-name $WebappSg `
    --description "webscraper admin webapp" --vpc-id $Vpc `
    --query GroupId --output text --region $Region).Trim()
  Ok "created security group $SgId"
}
$MyIp = (Invoke-RestMethod https://checkip.amazonaws.com).Trim()
# Ingress rules are idempotent-ish: swallow "Duplicate" errors.
Test-Aws ec2 authorize-security-group-ingress --group-id $SgId --protocol tcp --port 22  --cidr "$MyIp/32" --region $Region | Out-Null
Test-Aws ec2 authorize-security-group-ingress --group-id $SgId --protocol tcp --port 80  --cidr 0.0.0.0/0 --region $Region | Out-Null
Test-Aws ec2 authorize-security-group-ingress --group-id $SgId --protocol tcp --port 443 --cidr 0.0.0.0/0 --region $Region | Out-Null
Ok "ingress: 22 from $MyIp/32, 80+443 from anywhere"

if (Test-Aws ec2 describe-key-pairs --key-names $KeyName --region $Region) {
  Skip "key pair $KeyName already exists (private key was saved on first run)"
} else {
  $pem = Join-Path $RepoRoot "$KeyName.pem"
  aws ec2 create-key-pair --key-name $KeyName --query KeyMaterial --output text --region $Region |
    Out-File -Encoding ascii $pem
  Ok "created key pair -> $pem  (keep it; it's git-ignored via *.pem)"
}

# ============================================================================
# Phase 9 - EC2 instance + Elastic IP (self-bootstrapping via user-data)
# ============================================================================
Head "Phase 9 - EC2 instance + Elastic IP"
$existing = (aws ec2 describe-instances `
  --filters "Name=tag:Name,Values=$InstanceTag" "Name=instance-state-name,Values=pending,running,stopping,stopped" `
  --query "Reservations[0].Instances[0].InstanceId" --output text --region $Region 2>$null)
if ($existing -and $existing -ne "None") {
  Skip "instance $existing already tagged $InstanceTag - leaving it as-is"
  $InstanceId = $existing
  $PubIp = (aws ec2 describe-instances --instance-ids $InstanceId `
    --query "Reservations[0].Instances[0].PublicIpAddress" --output text --region $Region).Trim()
} else {
  # Allocate the Elastic IP FIRST so we can bake it into the instance's .env
  # (SITE_ADDRESS) via user-data before launch.
  $Alloc = (aws ec2 allocate-address --domain vpc --query AllocationId --output text --region $Region).Trim()
  $PubIp = (aws ec2 describe-addresses --allocation-ids $Alloc --query "Addresses[0].PublicIp" --output text --region $Region).Trim()
  Ok "allocated Elastic IP $PubIp"

  if (-not $AdminPassword) { $AdminPassword = New-UrlSafeSecret 12; $script:GeneratedPw = $AdminPassword }
  $SecretKey = New-UrlSafeSecret 48

  # Render the on-box bootstrap (mirrors terraform/user_data.sh.tftpl) with the
  # FARGATE_SECURITY_GROUP added so the webapp can auto-dispatch bulk crawls.
  $userData = @"
#!/bin/bash
set -euxo pipefail
dnf update -y
dnf install -y docker git
systemctl enable --now docker
usermod -aG docker ec2-user
mkdir -p /usr/local/lib/docker/cli-plugins
curl -SL "https://github.com/docker/compose/releases/latest/download/docker-compose-linux-x86_64" -o /usr/local/lib/docker/cli-plugins/docker-compose
chmod +x /usr/local/lib/docker/cli-plugins/docker-compose
BUILDX_VER=v0.19.3
curl -SL "https://github.com/docker/buildx/releases/download/`${BUILDX_VER}/buildx-`${BUILDX_VER}.linux-amd64" -o /usr/local/lib/docker/cli-plugins/docker-buildx
chmod +x /usr/local/lib/docker/cli-plugins/docker-buildx
install -d -o ec2-user -g ec2-user /opt/app
git clone --branch "$RepoBranch" "$RepoUrl" /opt/app/repo
APP_DIR="/opt/app/repo/webscraper"
cd "`$APP_DIR"
set +x
cat > "`$APP_DIR/.env" <<'ENVEOF'
SECRET_KEY=$SecretKey
SESSION_MAX_AGE_SECONDS=43200
ADMIN_USERNAME=$AdminUsername
ADMIN_PASSWORD=$AdminPassword
SITE_ADDRESS=$PubIp
LAMBDA_FUNCTION_NAME=$LambdaFn
AWS_REGION=$Region
AWS_DEFAULT_REGION=$Region
S3_ENABLED=true
S3_BUCKET=$Bucket
VISITED_STORE_BACKEND=dynamodb
DYNAMODB_TABLE=$Table
FARGATE_SECURITY_GROUP=
ECS_CLUSTER=$BulkCluster
ECS_TASK_FAMILY=$BulkFamily
BULK_URL_THRESHOLD=10
ENVEOF
chown ec2-user:ec2-user "`$APP_DIR/.env"
chmod 600 "`$APP_DIR/.env"
set -x
docker compose up -d --build
echo "webscraper webapp bootstrap complete at `$(date -u)"
"@
  # FARGATE_SECURITY_GROUP is left empty here (the bulk SG is created later in
  # Phase 11). The webapp only needs it for *auto-dispatching* large lists to
  # Fargate; the primary bulk path (Actions workflow) uses the repo variable
  # instead. To enable webapp auto-dispatch later, set it in the instance .env.
  $udFile = Join-Path $env:TEMP "webscraper-userdata.sh"
  Set-Content -Path $udFile -Value $userData -Encoding ascii

  $Ami = (aws ssm get-parameters --names /aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64 `
    --query "Parameters[0].Value" --output text --region $Region).Trim()
  $InstanceId = (aws ec2 run-instances --image-id $Ami --instance-type $InstanceType `
    --key-name $KeyName --security-group-ids $SgId `
    --iam-instance-profile "Name=$WebappRole" `
    --user-data "file://$udFile" `
    --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=$InstanceTag}]" `
    --query "Instances[0].InstanceId" --output text --region $Region).Trim()
  Ok "launched instance $InstanceId"
  aws ec2 associate-address --instance-id $InstanceId --allocation-id $Alloc --region $Region | Out-Null
  Ok "associated Elastic IP $PubIp  ->  app will be at https://$PubIp (allow ~5 min for first boot/build)"
}
} # end -SkipEc2

# ============================================================================
# Phase 10 - GitHub OIDC provider + deploy role
# ============================================================================
if ($SkipCicd) { Head "Phase 10 - CI/CD OIDC"; Skip "-SkipCicd set" }
else {
Head "Phase 10 - GitHub OIDC deploy role"
$oidcArn = "arn:aws:iam::${Account}:oidc-provider/token.actions.githubusercontent.com"
if (Test-Aws iam get-open-id-connect-provider --open-id-connect-provider-arn $oidcArn) {
  Skip "OIDC provider already exists"
} else {
  aws iam create-open-id-connect-provider `
    --url https://token.actions.githubusercontent.com `
    --client-id-list sts.amazonaws.com | Out-Null
  Ok "created GitHub OIDC provider"
}
$trustResolved  = Resolve-Template "github-oidc-trust-policy.json"     "trust.resolved.json"
if (Test-Aws iam get-role --role-name $DeployRole) {
  Skip "role $DeployRole exists - refreshing trust policy"
  aws iam update-assume-role-policy --role-name $DeployRole `
    --policy-document "file://$trustResolved" | Out-Null
} else {
  aws iam create-role --role-name $DeployRole `
    --assume-role-policy-document "file://$trustResolved" | Out-Null
  Ok "created role $DeployRole"
}
$deployResolved = Resolve-Template "github-actions-deploy-policy.json" "deploy.resolved.json"
aws iam put-role-policy --role-name $DeployRole --policy-name "github-actions-deploy" `
  --policy-document "file://$deployResolved" | Out-Null
Ok "attached deploy policy (ECR push + Lambda update + SSM send-command)"
$DeployRoleArn = (aws iam get-role --role-name $DeployRole --query Role.Arn --output text).Trim()
}

# ============================================================================
# Phase 11 - Fargate bulk crawl
# ============================================================================
if ($SkipFargate) { Head "Phase 11 - Fargate bulk"; Skip "-SkipFargate set" }
else {
Head "Phase 11 - Fargate bulk crawl"
Test-Aws logs create-log-group --log-group-name $BulkLogGroup --region $Region | Out-Null
Ok "log group $BulkLogGroup"
if (Test-Aws ecs describe-clusters --clusters $BulkCluster --region $Region) {
  $active = (aws ecs describe-clusters --clusters $BulkCluster --query "clusters[0].status" --output text --region $Region 2>$null)
  if ($active -eq "ACTIVE") { Skip "cluster $BulkCluster active" }
  else { aws ecs create-cluster --cluster-name $BulkCluster --capacity-providers FARGATE --region $Region | Out-Null; Ok "created cluster $BulkCluster" }
} else {
  aws ecs create-cluster --cluster-name $BulkCluster --capacity-providers FARGATE --region $Region | Out-Null
  Ok "created cluster $BulkCluster"
}
# Task execution role (pull image + write logs)
if (-not (Test-Aws iam get-role --role-name $BulkExec)) {
  aws iam create-role --role-name $BulkExec --assume-role-policy-document "file://$AwsDir\ecs-tasks-trust-policy.json" | Out-Null
  Ok "created role $BulkExec"
} else { Skip "role $BulkExec exists" }
aws iam attach-role-policy --role-name $BulkExec `
  --policy-arn arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy | Out-Null
# Task role (what the crawler may do: S3 + DynamoDB - same policies as Lambda)
if (-not (Test-Aws iam get-role --role-name $BulkTask)) {
  aws iam create-role --role-name $BulkTask --assume-role-policy-document "file://$AwsDir\ecs-tasks-trust-policy.json" | Out-Null
  Ok "created role $BulkTask"
} else { Skip "role $BulkTask exists" }
aws iam put-role-policy --role-name $BulkTask --policy-name "$Project-s3" `
  --policy-document "file://$s3Resolved" | Out-Null
aws iam put-role-policy --role-name $BulkTask --policy-name "$Project-dynamo" `
  --policy-document "file://$dynamoResolved" | Out-Null
Ok "attached S3 + DynamoDB policies to $BulkTask"
# Let the GitHub deploy role register + run tasks (only if that role exists)
if (-not $SkipCicd) {
  $fargateResolved = Resolve-Template "github-actions-fargate-policy.json" "fargate.resolved.json"
  aws iam put-role-policy --role-name $DeployRole --policy-name "github-actions-fargate" `
    --policy-document "file://$fargateResolved" | Out-Null
  Ok "granted $DeployRole ECS run + PassRole"
}
# Egress security group for the tasks. $Vpc may be unset if -SkipEc2 was used.
if (-not $Vpc) { $Vpc = (aws ec2 describe-vpcs --filters "Name=isDefault,Values=true" --query "Vpcs[0].VpcId" --output text --region $Region).Trim() }
$BulkSgId = (aws ec2 describe-security-groups --filters "Name=group-name,Values=$BulkSg" `
  "Name=vpc-id,Values=$Vpc" --query "SecurityGroups[0].GroupId" --output text --region $Region 2>$null)
if ($BulkSgId -and $BulkSgId -ne "None") {
  Skip "bulk security group $BulkSg = $BulkSgId"
} else {
  $BulkSgId = (aws ec2 create-security-group --group-name $BulkSg `
    --description "webscraper bulk Fargate egress" --vpc-id $Vpc `
    --query GroupId --output text --region $Region).Trim()
  Ok "created bulk security group $BulkSgId (default egress allows all outbound)"
}
# Register the task definition (RunTask uses the latest revision of the family)
$taskdefResolved = Resolve-Template "fargate-taskdef.template.json" "taskdef.resolved.json"
aws ecs register-task-definition --cli-input-json "file://$taskdefResolved" --region $Region | Out-Null
Ok "registered task definition family $BulkFamily"
}

# ============================================================================
# Phase 12 - summary
# ============================================================================
Head "Phase 12 - DONE. Set these GitHub repo variables"
Write-Host ""
Write-Host "  Repo: Settings -> Secrets and variables -> Actions -> Variables" -ForegroundColor White
if ($DeployRoleArn) { Write-Host "    AWS_DEPLOY_ROLE_ARN   = $DeployRoleArn" -ForegroundColor Yellow }
if ($BulkSgId)      { Write-Host "    FARGATE_SECURITY_GROUP = $BulkSgId" -ForegroundColor Yellow }
Write-Host ""
Write-Host "  If you have the GitHub CLI authenticated, run instead:" -ForegroundColor White
if ($DeployRoleArn) { Write-Host "    gh variable set AWS_DEPLOY_ROLE_ARN --repo JanSoetebeer/KML --body `"$DeployRoleArn`"" -ForegroundColor DarkGray }
if ($BulkSgId)      { Write-Host "    gh variable set FARGATE_SECURITY_GROUP --repo JanSoetebeer/KML --body `"$BulkSgId`"" -ForegroundColor DarkGray }
Write-Host ""
if (-not $SkipEc2 -and $PubIp) { Write-Host "  Webapp:  https://$PubIp   (self-signed cert; first boot ~5 min)" -ForegroundColor White }
if ($script:GeneratedPw) { Write-Host "  Seed admin password (generated): $($script:GeneratedPw)  (user: $AdminUsername)" -ForegroundColor Magenta }
Write-Host ""
Write-Host "  Launch a bulk crawl once the image is pushed:" -ForegroundColor White
Write-Host "    aws s3 cp `"hs_liste_ready_for_import 1.csv`" s3://$Bucket/lists/unis.csv --region $Region" -ForegroundColor DarkGray
Write-Host "    then: Actions -> 'Bulk crawl (Fargate)' -> Run workflow -> urls_s3 = s3://$Bucket/lists/unis.csv" -ForegroundColor DarkGray
Write-Host ""
Ok "Stack rebuild complete for account $Account."
