"""
Fargate/ECS **bulk-crawl** entrypoint.

The same container image that serves the Lambda (interactive) path runs the bulk
path on Fargate — no 15-minute timeout, more memory, ephemeral disk — by
overriding the container entrypoint to ``python bulk_run.py`` in the ECS task
definition (which bypasses the Lambda runtime interface). Everything else is
shared: the crawler, the ``mlclassifier`` model, the S3 output bucket, and the
DynamoDB visited store.

Configuration is entirely environment-driven (baked into the task definition and
overridable per launch via ``aws ecs run-task``):

    BULK_URLS_S3    s3://bucket/key of a URL list (.csv / .txt / .html). Preferred.
    BULK_URLS       Whitespace/comma-separated URLs (used only if BULK_URLS_S3 unset).
    BULK_BATCH_ID   Correlation id → s3://<bucket>/manifests/<id>.jsonl (default: uuid).
    CRAWL_PROFILE   Extraction profile (e.g. modulhandbuch | generic | html-content).
    BULK_MAX_JOBS   Concurrent per-university crawls (default: MAX_CONCURRENT_JOBS).
    FILE_TYPES      Optional comma-separated extension override (e.g. "pdf,docx").
    BULK_FORCE      "true" to ignore the visited store and re-crawl.

Crawl breadth/depth use the usual ``CRAWL_MAX_DEPTH`` / ``CRAWL_MAX_PAGES`` /
``MAX_ITEMS_PER_RUN`` env vars — raise them for bulk in the task definition (a
Fargate task has hours, not 15 minutes).

Exit code mirrors ``run_batch``: 0 = all jobs ok, 1 = no URLs, 2 = a job errored.
"""

import logging
import os
import sys
import tempfile
import uuid
from pathlib import Path
from urllib.parse import urlparse

os.environ.setdefault("SCRAPY_SETTINGS_MODULE", "webscraper.settings")

from webscraper.utils.url_sources import (  # noqa: E402 — after settings env is set
    extract_urls_from_csv_text,
    extract_urls_from_html_text,
    extract_urls_from_text_lines,
)

logger = logging.getLogger("bulk_run")


def _download_s3(uri: str) -> str:
    """Download an ``s3://bucket/key`` object to a temp file and return its path."""
    import boto3

    parsed = urlparse(uri)
    bucket, key = parsed.netloc, parsed.path.lstrip("/")
    suffix = Path(key).suffix or ".txt"
    fd, path = tempfile.mkstemp(suffix=suffix, dir="/tmp")
    os.close(fd)
    boto3.client("s3").download_file(bucket, key, path)
    logger.info("Downloaded %s → %s", uri, path)
    return path


def _urls_from_file(path: str) -> list[str]:
    """Extract URLs from a .csv / .html / .txt list (mirrors run.py's parsing)."""
    raw = Path(path).read_text(encoding="utf-8-sig")
    suffix = Path(path).suffix.lower()
    if suffix == ".csv":
        return extract_urls_from_csv_text(raw)
    if suffix in (".html", ".htm"):
        return extract_urls_from_html_text(raw)
    return extract_urls_from_text_lines(raw)


def _collect_urls() -> list[str]:
    """Resolve the URL list from BULK_URLS_S3 (preferred) or BULK_URLS."""
    s3_uri = os.getenv("BULK_URLS_S3", "").strip()
    if s3_uri:
        logger.info("Resolving URL list from %s", s3_uri)
        return _urls_from_file(_download_s3(s3_uri))
    raw = os.getenv("BULK_URLS", "").strip()
    if raw:
        # Accept comma- or whitespace-separated URLs.
        return [u.strip() for u in raw.replace(",", "\n").split() if u.strip()]
    return []


def main() -> int:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )
    # Imported lazily so logging is configured first and the module is only
    # loaded inside the container (keeps import errors localised to runtime).
    from run import run_batch

    urls = _collect_urls()
    seen: set[str] = set()
    ordered: list[str] = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            ordered.append(u)

    if not ordered:
        logger.error("No URLs resolved — set BULK_URLS_S3 (preferred) or BULK_URLS.")
        return 1

    file_types = None
    if os.getenv("FILE_TYPES"):
        file_types = [p.strip() for p in os.getenv("FILE_TYPES").split(",") if p.strip()]

    logger.info(
        "Bulk crawl starting — %d URL(s)  profile=%s  max_jobs=%s  depth=%s pages=%s",
        len(ordered), os.getenv("CRAWL_PROFILE", "(settings default)"),
        os.getenv("BULK_MAX_JOBS", os.getenv("MAX_CONCURRENT_JOBS", "8")),
        os.getenv("CRAWL_MAX_DEPTH"), os.getenv("CRAWL_MAX_PAGES"),
    )

    return run_batch(
        urls=ordered,
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        max_jobs=int(os.getenv("BULK_MAX_JOBS", os.getenv("MAX_CONCURRENT_JOBS", "8"))),
        ping=os.getenv("SCRAPE_PING", "true").lower() == "true",
        force=os.getenv("BULK_FORCE", "false").lower() == "true",
        batch_id=os.getenv("BULK_BATCH_ID") or uuid.uuid4().hex,
        file_types=file_types,
        profile=os.getenv("CRAWL_PROFILE"),
    )


if __name__ == "__main__":
    sys.exit(main())
