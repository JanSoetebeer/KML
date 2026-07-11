"""
AWS Lambda handler for the webscraper.

The handler runs the scraper as a **subprocess** (``python run.py <urls...>``)
rather than in-process, because Twisted's reactor cannot be restarted inside a
single process — a warm Lambda container would otherwise crash on its second
invocation. See :func:`handler` for details.

Deployment (container image — recommended)
------------------------------------------
Scrapy depends on compiled libraries (lxml, Twisted, cryptography), so a
container image is far simpler than a ZIP. Full step-by-step instructions —
including S3 bucket and IAM setup — live in ``DEPLOY_AWS.md``. Summary:

- ``Dockerfile`` builds an image with the AWS Lambda Python base image.
- Lambda handler is ``lambda_handler.handler``.
- Required Lambda environment variables:
    S3_ENABLED=true
    S3_BUCKET=<your-bucket>
    LOCAL_ENABLED=false           # project dir is read-only on Lambda
    LOG_DIR=/tmp/logs             # only /tmp is writable on Lambda
    VISITED_STORE_PATH=/tmp/visited.json
  Credentials come from the Lambda execution **IAM role** — never hardcode keys.
- Timeout: >= 5 min for document-heavy pages. Memory: 512 MB+.

Expected event payloads
------------------------
Direct invoke / EventBridge::

    {"url": "https://example.com/resources"}        # single URL
    {"urls": ["https://a.com", "https://b.com"]}     # multiple URLs
    # optional fields: "job_id", "log_level", "max_jobs"

SQS (batch)::

    {"Records": [{"body": "{\\"url\\": \\"https://a.com\\"}"}, ...]}

Response
--------
Returns ``{"statusCode": ..., "body": "..."}`` (API Gateway proxy compatible).

TODO (before production)
------------------------
- Back the visited store with DynamoDB (the /tmp JSON file does not persist
  reliably across invocations).
- Add SQS partial-batch-failure handling + a Dead Letter Queue.
- Emit a structured completion event to EventBridge.
"""

import json
import logging
import os
import subprocess
import sys
import uuid

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Directory containing run.py (this file's directory).
_PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))

# Exit codes returned by run.py / run_batch().
_EXIT_OK = 0
_EXIT_NO_URLS_OR_INVALID = 1
_EXIT_JOB_ERROR = 2


def _extract_urls(event: dict) -> list[str]:
    """
    Pull one or more URLs out of a Lambda event.

    Supported shapes
    ----------------
    - Direct invoke / EventBridge: ``{"url": "..."}`` or ``{"urls": ["...", ...]}``
    - SQS: ``{"Records": [{"body": "<json>"}, ...]}`` where each body is the
      direct shape above.
    """
    # SQS / batch trigger
    if "Records" in event:
        urls: list[str] = []
        for record in event["Records"]:
            body = record.get("body", "{}")
            try:
                parsed = json.loads(body)
            except (json.JSONDecodeError, TypeError):
                # Treat a raw string body as a URL
                if isinstance(body, str) and body.strip():
                    urls.append(body.strip())
                continue
            urls.extend(_extract_urls(parsed))
        return urls

    if "urls" in event and isinstance(event["urls"], list):
        return [u for u in event["urls"] if u]

    if event.get("url"):
        return [event["url"]]

    return []


def handler(event: dict, context) -> dict:
    """
    Lambda entry point.

    Runs the scraper in a **subprocess** (``python run.py <urls...>``). This is
    deliberate: Twisted's reactor cannot be restarted within a single process,
    so running in-process would crash on the second (warm) invocation with
    ``ReactorNotRestartable``. A fresh subprocess per invocation avoids this.

    Parameters
    ----------
    event:
        Lambda event payload (see module docstring for supported shapes).
    context:
        Lambda context object (used for the remaining-time budget).

    Returns
    -------
    dict
        ``{"statusCode": 200, "body": "..."}`` on success or
        ``{"statusCode": 4xx/5xx, "body": "..."}`` on failure.
    """
    urls = _extract_urls(event)
    if not urls:
        return {
            "statusCode": 400,
            "body": json.dumps({"error": "No 'url' or 'urls' found in event."}),
        }

    job_id = event.get("job_id") or uuid.uuid4().hex
    log_level = event.get("log_level", os.getenv("LOG_LEVEL", "INFO"))
    max_jobs = str(event.get("max_jobs", os.getenv("MAX_CONCURRENT_JOBS", "10")))
    file_types = event.get("file_types")  # list or comma-separated string

    logger.info(
        "Lambda invoked — job_id=%s  urls=%s  file_types=%s",
        job_id,
        urls,
        file_types,
    )

    cmd = [
        sys.executable,
        "run.py",
        *urls,
        "--max-jobs",
        max_jobs,
        "--log-level",
        log_level,
    ]

    if file_types:
        if isinstance(file_types, (list, tuple)):
            file_types = ",".join(str(ft) for ft in file_types)
        cmd += ["--file-types", str(file_types)]

    # Leave a safety margin so we can return a response before Lambda times out.
    timeout_s = 600.0
    if context is not None and hasattr(context, "get_remaining_time_in_millis"):
        timeout_s = max(5.0, context.get_remaining_time_in_millis() / 1000.0 - 5.0)

    try:
        result = subprocess.run(
            cmd,
            cwd=_PROJECT_DIR,
            env=os.environ.copy(),  # inherits S3_*, LOG_DIR, VISITED_STORE_PATH, etc.
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
    except subprocess.TimeoutExpired:
        logger.error("[%s] Scrape timed out after %.0fs", job_id, timeout_s)
        return {
            "statusCode": 504,
            "body": json.dumps(
                {"job_id": job_id, "status": "timeout", "urls": urls}
            ),
        }

    # Forward the subprocess output to CloudWatch for visibility.
    if result.stdout:
        logger.info("[%s] scraper stdout:\n%s", job_id, result.stdout)
    if result.stderr:
        logger.warning("[%s] scraper stderr:\n%s", job_id, result.stderr)

    summary = _extract_summary(result.stdout)

    code = result.returncode
    if code == _EXIT_OK:
        return {
            "statusCode": 200,
            "body": json.dumps(
                {"job_id": job_id, "status": "completed", "urls": urls,
                 "summary": summary}
            ),
        }
    if code == _EXIT_NO_URLS_OR_INVALID:
        return {
            "statusCode": 422,
            "body": json.dumps(
                {"job_id": job_id, "status": "no_urls_or_invalid", "urls": urls,
                 "summary": summary}
            ),
        }
    return {
        "statusCode": 500,
        "body": json.dumps(
            {"job_id": job_id, "status": "job_error", "urls": urls,
             "exit_code": code, "summary": summary}
        ),
    }


# Must match run.py's SUMMARY_MARKER.
_SUMMARY_MARKER = "__SCRAPE_SUMMARY__"


def _extract_summary(stdout: str | None) -> dict | None:
    """Pull the JSON run summary printed by run.py out of the subprocess stdout."""
    if not stdout:
        return None
    for line in stdout.splitlines():
        idx = line.find(_SUMMARY_MARKER)
        if idx != -1:
            payload = line[idx + len(_SUMMARY_MARKER):].strip()
            try:
                return json.loads(payload)
            except (json.JSONDecodeError, ValueError):
                return None
    return None
