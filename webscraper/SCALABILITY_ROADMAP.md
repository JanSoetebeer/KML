# Scalability Roadmap

How the scraper + classifier system should evolve from "works for on-demand demo
scrapes" to "can harvest Modulhandbücher across all German universities."

## The core problem

Today every scrape runs in **one AWS Lambda invocation** (the webapp invokes it
synchronously; `run.py` runs the Scrapy crawl as a subprocess). That is a great
fit for a *small, interactive* scrape — a few catalog URLs, results in under a
minute, pay-per-call, nothing running when idle.

It does **not** fit a *large bulk crawl*, because of three hard Lambda limits:

1. **15-minute wall-clock timeout.** A deep crawl of one big university — or many
   universities in one call — exceeds it and is killed mid-run.
2. **In-memory buffering.** `S3Pipeline` holds each downloaded file in RAM before
   uploading (`upload_fileobj(BytesIO(item["content"]))`). Thousands of PDFs /
   large files → out-of-memory.
3. **One invocation = one batch.** All URLs in a run share the single 15-minute
   budget and one container's memory.

The visited-URL dedup (DynamoDB) and the S3 output store already scale fine; the
bottleneck is purely the **crawl compute**.

## Design principle: two workloads, one codebase

Do **not** replace Lambda. Split the work by shape and route to the right runtime
— both run the **same Docker image** (`webscraper/Dockerfile`, which already
bundles the crawler + `mlclassifier` + model):

| Workload | Example | Runtime | Why |
|---|---|---|---|
| **Interactive / small** | reviewer scrapes a few program pages from the UI | **Lambda** (keep as-is) | fast, cheap, on-demand, already built |
| **Bulk / deep** | harvest all universities for training data | **Fargate/ECS task** (new) | no time limit, more memory, ephemeral disk |

A single "deep crawl?" toggle (or a URL-count threshold) in the webapp decides
which one to dispatch.

## Immediate stopgap (no new infra)

Until the phases below land, run a big crawl **on the EC2 box you already have**
(or locally), with `S3_ENABLED=true` and raised limits:

```bash
CRAWL_MAX_DEPTH=3 CRAWL_MAX_PAGES=300 MAX_ITEMS_PER_RUN=0 \
  python run.py --urls-file catalog_urls.csv --max-jobs 8
```

Same S3 output as Lambda, no 15-minute ceiling. This is the manual version of
what Phase 2 automates.

---

## Phase 1 — Quick wins (low effort, high value)

**1a. Stream downloads to S3 instead of buffering in RAM.**
Stage each file to `/tmp` (Lambda `/tmp` is configurable up to 10 GB), classify
from the temp file, upload, delete. Removes the memory ceiling for *every*
compute path. *(Code: `S3Pipeline` + `ClassificationPipeline`.)*

**1b. Per-university SQS fan-out for breadth.**
Instead of one invocation for N universities, enqueue **one SQS message per
university**; Lambda processes **one uni per invocation**, each with its own
15-minute budget, hundreds in parallel. The handler already parses SQS `Records`
— this is mostly an SQS queue + event-source mapping + an "enqueue" entry point.
Solves "many universities at once" without new compute. *(Best for broad,
shallow/medium crawls; a single very deep uni still needs Phase 2.)*

**Unblocks:** medium-scale runs (dozens–hundreds of unis) stay on serverless.

## Phase 2 — Bulk-crawl compute (the "switch")

**Run the same image as an on-demand Fargate/ECS task** with hours of runtime,
larger memory, and ephemeral disk. Triggered by the webapp ("Full crawl") or a
CI/cron job via `ecs:RunTask`. This is the primary answer to *"switch it somehow
for a large crawl."*

- Route by size: webapp dispatches **Lambda** for interactive, **Fargate** for a
  deep/full harvest.
- Reuses the existing Docker image, S3 output, and DynamoDB visited store — no
  code rewrite, just a new task definition + IAM role.

**Unblocks:** the full all-universities training-data harvest.

## Phase 3 — Decouple classification from crawling

Today scoring runs **inline on the crawl reactor thread** (a large PDF briefly
blocks other jobs). Split it:

- Crawl only **downloads to S3**.
- An **S3 `ObjectCreated` event** triggers a small **classification Lambda** that
  scores the object and writes its manifest/decision.

Now crawl throughput and ML scoring scale independently, and a slow model never
slows the crawl. Consider writing per-document decisions to **DynamoDB** (instead
of one JSONL manifest per run) so results stay queryable at scale.

**Unblocks:** crawl speed independent of model speed; cleaner ret’s.

## Phase 4 — Durable job orchestration

The webapp's job registry is **in-memory** (`_JOBS`, lost on restart) and the
Lambda call is synchronous.

- Move job state to a **DynamoDB job table** (job id → status, counts, compute
  type, S3 prefix) that both Lambda and Fargate report into.
- Webapp **enqueues → returns job id → polls the table** (the async UI pattern
  already exists; make its backing store durable).
- Optional: **Step Functions** to orchestrate a full harvest — fan-out per uni →
  aggregate → signal "ready to retrain."

**Unblocks:** reliable progress tracking across many long-running jobs.

## Phase 5 — Scale the data + ML loop

- **Scheduled / triggered retrain.** Keep training local + cheap (seconds), but
  add a CI cron or a "≥ N new verdicts" trigger to `feedback-retrain` so the
  model refreshes without manual runs.
- **Model registry in S3.** Version each `module_classifier.joblib`, load the
  active one at startup (the webapp `SYS_AI_MODELS` table already stubs this), so
  a retrain → deploy is a config flip, not an image rebuild.
- **Cost / hygiene controls.** S3 lifecycle rules to expire raw `scraped/…`
  objects after they're ingested; DynamoDB **TTL** on visited entries to allow
  periodic re-crawls; pin `scikit-learn` so a retrained model always loads.

---

## "When to use what" — decision cheat sheet

- **A reviewer scrapes a handful of catalog/program URLs** → Lambda (interactive).
- **Broad sweep of many universities, shallow/medium depth** → SQS + Lambda
  fan-out (Phase 1b).
- **Deep crawl of a big site, or the full all-universities harvest** →
  Fargate/ECS task (Phase 2), or the EC2 stopgap today.
- **Scoring downloaded documents** → inline for now; S3-event Lambda at scale
  (Phase 3).

## What to keep / avoid

- **Keep Lambda** for the interactive path — it is genuinely the right tool there.
- **Reuse the one Docker image** everywhere; don't fork the crawler per runtime.
- **Don't reach for Kubernetes** — Fargate covers the unbounded-runtime need with
  far less operational overhead for this project's size.
- The **DynamoDB visited store** already scales; no change needed beyond optional
  TTL for re-crawls.

## Suggested order

1. Phase 1a (streaming) + 1b (SQS fan-out) — biggest scale gain per unit effort.
2. Phase 2 (Fargate) — unblocks the real bulk harvest.
3. Phase 4 (durable jobs) — needed once long-running jobs are common.
4. Phase 3 (decoupled classification) + Phase 5 (loop scaling) — polish for
   steady-state operation.
