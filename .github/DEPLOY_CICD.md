# CI/CD: auto-deploy on push to `main`

Two GitHub Actions workflows deploy the project whenever you push to `main`:

| Workflow | Triggers on changes to | What it does |
|---|---|---|
| [`deploy-lambda.yml`](workflows/deploy-lambda.yml) | `webscraper/**`, `mlclassifier/**` (not webapp-only / docs) | Build the scraper+ML image from the repo root → push to ECR → `lambda update-function-code` |
| [`deploy-webapp.yml`](workflows/deploy-webapp.yml) | `webscraper/webapp/**`, `webscraper/webscraper/**`, compose/Dockerfile.webapp, `mlclassifier/**` | Via **SSM Run Command**: `git pull` + `docker compose up -d --build` on the EC2 instance |

Both authenticate to AWS with **OIDC** (no long-lived keys in GitHub). This is
**independent of Terraform** — it deploys onto your existing, hand-created
Lambda/EC2, and never touches Terraform state. You do **not** need to fix the
Terraform import problem to use this.

Shell snippets below are PowerShell (Windows); run them once with the AWS CLI
configured (`aws sts get-caller-identity`). `$ACCOUNT`, `$REGION` as in the other
deploy docs (`eu-central-1`).

---

## One-time AWS setup

```powershell
$REGION  = "eu-central-1"
$ACCOUNT = (aws sts get-caller-identity --query Account --output text)
$ROLE    = "github-actions-deploy"
```

### 1. Create the GitHub OIDC provider (skip if it already exists)

```powershell
aws iam create-open-id-connect-provider `
  --url https://token.actions.githubusercontent.com `
  --client-id-list sts.amazonaws.com
```
> If it already exists you'll get `EntityAlreadyExists` — that's fine, move on.

### 2. Create the deploy role (trusts your repo's `main` via OIDC)

The two policy templates are in [`../webscraper/aws/`](../webscraper/aws/).
Substitute `ACCOUNT_ID` / `REGION` first.

```powershell
# Trust policy: who can assume the role (this repo, main branch).
# NOTE: -Encoding ascii is required — the AWS CLI rejects any non-ASCII byte
# (or a UTF-16/BOM file) with "must contain only printable ASCII characters".
(Get-Content webscraper/aws/github-oidc-trust-policy.json) `
  -replace "ACCOUNT_ID", $ACCOUNT | Set-Content trust.resolved.json -Encoding ascii
aws iam create-role --role-name $ROLE `
  --assume-role-policy-document file://trust.resolved.json

# Permissions: ECR push, Lambda update, SSM send-command to the webapp instance.
(Get-Content webscraper/aws/github-actions-deploy-policy.json) `
  -replace "ACCOUNT_ID", $ACCOUNT -replace "REGION", $REGION | Set-Content deploy.resolved.json -Encoding ascii
aws iam put-role-policy --role-name $ROLE `
  --policy-name github-actions-deploy --policy-document file://deploy.resolved.json

$ROLE_ARN = (aws iam get-role --role-name $ROLE --query Role.Arn --output text)
$ROLE_ARN   # <-- you'll paste this into GitHub in step 4
```

### 3. Let the instance receive SSM commands

The webapp deploy runs commands on the box through Systems Manager, so:

- **Instance role needs the SSM policy.** Attach the AWS-managed policy to the
  EC2 instance's role (the role from `DEPLOY_WEBAPP_EC2.md`, e.g.
  `webscraper-webapp-role`):

  ```powershell
  aws iam attach-role-policy `
    --role-name webscraper-webapp-role `
    --policy-arn arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore
  ```

- **SSM agent** ships enabled on Amazon Linux 2023 — nothing to install. Confirm
  the instance shows up as *Managed* (may take a minute after attaching the role):

  ```powershell
  aws ssm describe-instance-information `
    --query "InstanceInformationList[].{Id:InstanceId,Ping:PingStatus}" --region $REGION
  ```
  If it never appears, the instance may need a reboot to pick up the new role,
  and its subnet needs outbound HTTPS to the SSM endpoints (a default-VPC public
  subnet with the Elastic IP already does).

- **Instance `Name` tag** must be `webscraper-webapp` (both the manual guide and
  Terraform set this). The workflow finds the instance by that tag; the deploy
  policy also scopes `ssm:SendCommand` to it.

---

## One-time GitHub setup

In the repo: **Settings → Secrets and variables → Actions → Variables** (these
are *variables*, not secrets — none of them are sensitive):

| Variable | Value | Used by |
|---|---|---|
| `AWS_DEPLOY_ROLE_ARN` | the `$ROLE_ARN` from step 2 | both workflows |
| `WEBAPP_DIR` | *(optional)* absolute path to the dir containing `docker-compose.yml` on the instance, if auto-detect fails | webapp |

The workflows hard-code `AWS_REGION: eu-central-1`, the ECR repo `webscraper`,
the Lambda `webscraper`, and the instance tag `webscraper-webapp`. Edit the `env:`
block at the top of each workflow if any of those differ.

---

## Private repo? (git access on the instance)

The webapp deploy does `git pull` **on the instance**, so if
`JanSoetebeer/KML` is **private**, the instance's clone must be able to
authenticate. One-time, on the box (via SSH or `aws ssm start-session`):

- easiest: add a **read-only deploy key** (`ssh-keygen` on the instance, add the
  public key under GitHub repo → Settings → Deploy keys), then set the remote to
  SSH: `git -C <TOP> remote set-url origin git@github.com:JanSoetebeer/KML.git`;
- or store a fine-grained PAT in the https remote URL / a credential helper.

If the repo is **public**, nothing to do.

The Lambda deploy is unaffected — GitHub's runner checks the code out itself and
builds the image; the instance is not involved.

---

## First run & verification

1. Push a change to `main` (or run either workflow manually from the **Actions**
   tab → *Run workflow*).
2. **Lambda:** the run ends by printing the new image URI; confirm with
   `aws lambda get-function --function-name webscraper --query "Code.ImageUri"`.
3. **Webapp:** the run prints the instance's `docker compose ps` at the end; or
   reload `https://<ELASTIC_IP>`.

### Rollback
- **Lambda:** re-point to a previous image tag —
  `aws lambda update-function-code --function-name webscraper --image-uri <ECR>/webscraper:<old-sha>`
  (every build is tagged with its commit SHA, so old images remain in ECR).
- **Webapp:** revert the commit on `main` and push — the next run redeploys the
  reverted tree. (Data in the `webapp_data` volume — `app.db`, `Log.txt` — is
  untouched by deploys.)

---

## Notes / trade-offs

- **The webapp image builds on the instance** (a 2 GB `t3.small`). That matches
  your current manual flow. If builds get slow or OOM, switch to building the
  image in CI and pulling it (needs a compose change + ECR pull perms on the
  instance role) — ask and this can be added.
- **Retrained model still needs a Lambda redeploy.** After
  `mlclassifier feedback-retrain` produces a new `module_classifier.joblib`,
  commit it to `main` — that triggers `deploy-lambda.yml`, which bakes the new
  model into the image. (The model is git-tracked for exactly this reason.)
- **Path filters** keep a webapp-only change from rebuilding the Lambda and vice
  versa; shared code under `webscraper/webscraper/**` and `mlclassifier/**`
  triggers both, which is correct.
