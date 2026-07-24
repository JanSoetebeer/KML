# Bulk crawl on AWS Fargate

The **bulk** path for deep or many-university harvests — no 15-minute Lambda
timeout, more memory, ephemeral disk. It runs the **same container image** the
Lambda runs (built + pushed by `deploy-lambda.yml`), overriding the container
entrypoint to `python bulk_run.py` so it bypasses the Lambda runtime. Output goes
to the **same** S3 bucket + DynamoDB visited store, so results appear in the
existing review UI unchanged.

```
                 interactive (a few URLs, <15 min)        bulk (deep / many unis, hours)
Webapp / Actions ─────────► Lambda (webscraper) ─┐   ┌─► Fargate task (webscraper-bulk)
                                                 ├──►│      python bulk_run.py
   same image, S3 bucket, DynamoDB visited store ┘   └──► S3 (scraped/ + manifests/) + DynamoDB
```

When to use which:

| Job | Runtime |
|---|---|
| Reviewer scrapes a handful of program URLs | **Lambda** (existing, unchanged) |
| Deep crawl of a big site, or the full all-universities harvest | **Fargate** (this doc) |

This is **independent of Terraform** (deprecated) — pure AWS CLI + OIDC, matching
[`.github/DEPLOY_CICD.md`](../.github/DEPLOY_CICD.md). PowerShell snippets below;
run the one-time setup once with the AWS CLI configured.

---

## One-time AWS setup

```powershell
$REGION  = "eu-central-1"
$ACCOUNT = (aws sts get-caller-identity --query Account --output text)
```

### 1. CloudWatch log group

```powershell
aws logs create-log-group --log-group-name /ecs/webscraper-bulk --region $REGION
# EntityAlreadyExists is fine.
```

### 2. ECS cluster (Fargate — no EC2 to manage)

```powershell
aws ecs create-cluster --cluster-name webscraper-bulk `
  --capacity-providers FARGATE --region $REGION
```

### 3. Task **execution** role (pulls the image, writes logs)

```powershell
aws iam create-role --role-name webscraper-bulk-exec `
  --assume-role-policy-document file://webscraper/aws/ecs-tasks-trust-policy.json
aws iam attach-role-policy --role-name webscraper-bulk-exec `
  --policy-arn arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy
```

### 4. Task **role** (what the crawler itself may do: S3 + DynamoDB)

Reuses the exact policies the Lambda already uses.

```powershell
aws iam create-role --role-name webscraper-bulk-task `
  --assume-role-policy-document file://webscraper/aws/ecs-tasks-trust-policy.json

# S3 read/write to the output bucket (bucket name is hard-coded in the file).
aws iam put-role-policy --role-name webscraper-bulk-task `
  --policy-name webscraper-s3 --policy-document file://webscraper/aws/s3-policy.json

# DynamoDB visited store.
aws iam put-role-policy --role-name webscraper-bulk-task `
  --policy-name webscraper-dynamo --policy-document file://webscraper/aws/dynamodb-policy.json
```

### 5. Let the GitHub deploy role register + run tasks

Adds ECS + `iam:PassRole` (scoped to the two roles above) to the existing
`github-actions-deploy` role. Substitute `ACCOUNT_ID` first.

```powershell
(Get-Content webscraper/aws/github-actions-fargate-policy.json) `
  -replace "ACCOUNT_ID", $ACCOUNT | Set-Content fargate.resolved.json -Encoding ascii
aws iam put-role-policy --role-name github-actions-deploy `
  --policy-name github-actions-fargate --policy-document file://fargate.resolved.json
```

### 6. Network: an egress-enabled security group

Fargate tasks run in your VPC. In the **default VPC** a public subnet + a
security group that allows all outbound (no inbound) + `assignPublicIp=ENABLED`
is enough to reach university sites, S3 and DynamoDB — no NAT gateway needed.

```powershell
$VPC = (aws ec2 describe-vpcs --filters Name=isDefault,Values=true `
  --query "Vpcs[0].VpcId" --output text --region $REGION)
$SG = (aws ec2 create-security-group --group-name webscraper-bulk-sg `
  --description "webscraper bulk Fargate egress" --vpc-id $VPC `
  --query GroupId --output text --region $REGION)
# Default SG egress already allows all outbound; nothing else to add.
$SG   # <-- note this id for the GitHub variable below
```

### 7. GitHub repo variables

**Settings → Secrets and variables → Actions → Variables** (reuse
`AWS_DEPLOY_ROLE_ARN` from DEPLOY_CICD.md; add the SG):

| Variable | Value |
|---|---|
| `FARGATE_SECURITY_GROUP` | the `$SG` id from step 6 |
| `FARGATE_SUBNETS` | *(optional)* comma-separated subnet ids; auto-discovered from the default VPC if unset |

---

## Launch a bulk crawl

### A. Upload a URL list to S3

Any `.csv` (URL-column aware, like the webapp upload), `.txt`, or `.html`:

```powershell
aws s3 cp "hs_liste_ready_for_import 1.csv" `
  s3://webscraper-output-$ACCOUNT/lists/unis.csv --region $REGION
```

### B. Run it — from the Actions tab (recommended)

**Actions → Bulk crawl (Fargate) → Run workflow**, set `urls_s3` to
`s3://webscraper-output-<account>/lists/unis.csv`, pick a profile, adjust
depth/pages/cpu if desired. The workflow registers the task definition with the
latest image and launches one Fargate task.

### B′. …or from your machine

```bash
export FARGATE_SECURITY_GROUP=sg-xxxx
webscraper/deploy/fargate/run-bulk.sh s3://webscraper-output-<account>/lists/unis.csv modulhandbuch 8
```

### C. Watch + collect results

```powershell
aws logs tail /ecs/webscraper-bulk --follow --region $REGION
```

Scraped files land at `s3://webscraper-output-<account>/scraped/<host>/<job>/…`
and the run's classification manifest at
`s3://webscraper-output-<account>/manifests/<batch_id>.jsonl` — the same layout
the Lambda produces, so the webapp's results view reads it as-is.

---

## Webapp auto-dispatch (single URL → Lambda, large list → bulk)

The Scraping tab routes **automatically by URL count** — no separate button. A
single URL (or up to `BULK_URL_THRESHOLD`, default 10) goes to **Lambda** as
before; a larger uploaded CSV/list is dispatched to the **Fargate bulk** task.
The webapp uploads the URL list to `s3://<bucket>/lists/<job_id>.txt` and runs
the task with `BULK_BATCH_ID=<job_id>`, so the run's results land under the same
job id the review UI already uses. Bulk runs execute in the background: the tab
shows "läuft auf AWS Fargate …" and the results/classification appear under that
job id once the task finishes (reload to refresh — live tracking is Phase 4).

To enable it, the **EC2 webapp instance role** needs to run the task + pass the
task roles (it already has `s3:PutObject` for the list upload):

```powershell
(Get-Content webscraper/aws/webapp-ecs-policy.json) `
  -replace "ACCOUNT_ID", $ACCOUNT | Set-Content webapp-ecs.resolved.json -Encoding ascii
aws iam put-role-policy --role-name webscraper-webapp-role `
  --policy-name webapp-ecs --policy-document file://webapp-ecs.resolved.json
```

Then set these in the instance's `.env` (next to `docker-compose.yml`) and
`docker compose up -d`:

```
FARGATE_SECURITY_GROUP=sg-xxxxxxxx        # the SG from step 6 above (required)
FARGATE_SUBNETS=subnet-aaa,subnet-bbb     # optional; auto-discovered if unset
BULK_URL_THRESHOLD=10                      # URLs above this → bulk
# ECS_CLUSTER / ECS_TASK_FAMILY default to webscraper-bulk
```

If `FARGATE_SECURITY_GROUP` is unset the webapp keeps sending everything to
Lambda (a very large list would then risk the 15-min timeout — that's the signal
to configure bulk).

## Cost & time estimate

**Fargate pricing** (eu-central-1, Linux/x86): **$0.04456 / vCPU-hour** +
**$0.004865 / GB-hour**. The default task is **2 vCPU + 8 GB** ≈ **$0.13 / hour**
(ephemeral storage: first 20 GB free, so ~0). Billed per second while the task
runs; **nothing when idle** (no always-on cost, unlike the EC2 stopgap).

Throughput is governed by **politeness**, not CPU: `DOWNLOAD_DELAY=0.4s`,
2 requests/domain, 8 universities in parallel (`CONCURRENT_REQUESTS=16`). Rough
figures with the focused (best-first) crawl at `CRAWL_MAX_PAGES=300`:

| Harvest | Wall-clock | Fargate cost |
|---|---|---|
| ~30 universities | ~20–40 min | **< $0.10** |
| ~150 universities (your `hs_liste`) | **~1–2 hours** | **~$0.15–0.30** |
| ~400 German universities | ~2–4 hours | **well under $1** |
| One very deep single site (`CRAWL_MAX_PAGES=1000`) | ~15–40 min | a few cents |

Non-compute costs are negligible: S3 `PUT` ≈ $0.005 per 1,000 files, transient
storage a few GB at $0.023/GB-month, DynamoDB on-demand a few hundred writes.
**A full national harvest costs under a euro and finishes in an afternoon.**

Cheaper/faster than the alternatives for this workload: hundreds of 15-min Lambda
invocations would cost more compute and still cap each uni at 15 min; a
persistent EC2 box bills 24/7 even when idle.

### Going faster (sharding)

Wall-clock is dominated by per-domain politeness, so the lever is **more tasks in
parallel**, not a bigger task. Split the URL list into _k_ files and launch _k_
tasks (each with its own `BULK_BATCH_ID`); total vCPU-hours — and thus cost —
stay roughly the same while wall-clock drops ~_k_×. The DynamoDB visited store is
shared, so tasks won't re-crawl each other's URLs. Fargate's default account
limits comfortably allow a handful of concurrent tasks.

---

## Tuning knobs (task definition env, per-launch overridable)

| Var | Default | Effect |
|---|---|---|
| `CRAWL_MAX_DEPTH` | 3 | how deep same-subdomain link-following goes |
| `CRAWL_MAX_PAGES` | 300 | page budget per university (best-first spends it well) |
| `BULK_MAX_JOBS` | 8 | universities crawled concurrently |
| `CONCURRENT_REQUESTS` | 16 | global in-flight request cap (≈ 2 × BULK_MAX_JOBS) |
| `DOWNLOAD_DELAY` | 0.4 | politeness delay per domain (raise to be gentler) |
| `CRAWL_PROFILE` | modulhandbuch | extraction profile (also: generic, html-content) |
| `MAX_ITEMS_PER_RUN` | 0 | per-run download cap; 0 = unlimited (bulk) |

Raise CPU/memory (`cpu`/`memory` workflow inputs) only if you raise
`BULK_MAX_JOBS` a lot — the workload is I/O-bound, so 2 vCPU handles 8 parallel
crawls comfortably.
