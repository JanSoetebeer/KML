"""
AWS Lambda handler stub for the webscraper.

This module wires an AWS Lambda event to the same ``run()`` function used
by the CLI entrypoint (``run.py``), so the core logic is shared and
testable locally without Lambda.

Deployment notes
----------------
- Package the entire ``webscraper/`` directory plus this file into a Lambda
  ZIP or container image.
- Set the Lambda handler to ``lambda_handler.handler``.
- Pass all required environment variables (``S3_BUCKET``, ``S3_ENABLED``,
  ``AWS_DEFAULT_REGION``, etc.) as Lambda environment variables — do NOT
  hardcode credentials.
- Increase Lambda timeout to at least 5 minutes for pages with many documents.
- Recommended memory: 512 MB (adjust based on document sizes).

Expected event payload
----------------------
Trigger via SQS, EventBridge, API Gateway, or direct invocation::

    {
        "url": "https://example.com/resources",
        "job_id": "optional-custom-id",       // optional
        "log_level": "INFO"                    // optional, default "INFO"
    }

Response
--------
Returns a dict with ``statusCode`` and ``body`` keys, compatible with API
Gateway proxy integration.

TODO (before production)
------------------------
- Add SQS batch-item failure handling for partial batch retries.
- Add DLQ (Dead Letter Queue) for failed jobs.
- Emit a structured JSON event to CloudWatch / EventBridge on completion.
- Consider Step Functions for multi-step / long-running crawls.
"""

import json
import logging
import os
import uuid

logger = logging.getLogger(__name__)


def handler(event: dict, context) -> dict:
    """
    Lambda entry point.

    Parameters
    ----------
    event:
        Lambda event payload (see module docstring for expected shape).
    context:
        Lambda context object (unused, available for request ID etc.).

    Returns
    -------
    dict
        ``{"statusCode": 200, "body": "..."}`` on success or
        ``{"statusCode": 4xx/5xx, "body": "..."}`` on failure.
    """
    # Support SQS-wrapped events transparently
    if "Records" in event:
        record = event["Records"][0]
        event = json.loads(record.get("body", "{}"))

    url = event.get("url")
    if not url:
        return {
            "statusCode": 400,
            "body": json.dumps({"error": "Missing required field: 'url'"}),
        }

    job_id = event.get("job_id") or uuid.uuid4().hex
    log_level = event.get("log_level", os.getenv("LOG_LEVEL", "INFO"))

    logger.info("Lambda invoked — job_id=%s  url=%s", job_id, url)

    # Import here to avoid heavy Scrapy initialisation at cold-start import time
    from run import run as scraper_run

    exit_code = scraper_run(url=url, job_id=job_id, log_level=log_level, ping=True)

    if exit_code == 0:
        return {
            "statusCode": 200,
            "body": json.dumps({"job_id": job_id, "status": "completed", "url": url}),
        }
    elif exit_code == 1:
        return {
            "statusCode": 422,
            "body": json.dumps(
                {"job_id": job_id, "status": "validation_failed", "url": url}
            ),
        }
    else:
        return {
            "statusCode": 500,
            "body": json.dumps(
                {"job_id": job_id, "status": "crawl_error", "url": url}
            ),
        }
