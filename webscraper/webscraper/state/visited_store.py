"""
Persistent registry of already-scraped URLs.

Purpose
-------
- Avoid re-scraping the same site on repeated runs.
- Provide a loop-guard for future deep-crawling spiders (a spider can consult
  the store before following an internal link).

This is separate from Scrapy's in-memory ``RFPDupeFilter``, which only
deduplicates requests *within a single crawl*.  This store persists *across*
runs and across jobs.

Extension guide
---------------
To back the registry with DynamoDB / a SQL database instead of a JSON file:

1. Subclass :class:`BaseVisitedStore`.
2. Implement ``has_visited`` / ``mark_visited`` / ``all_visited``.
3. Construct your implementation in ``JobRunner`` (or inject it).

Nothing else in the codebase needs to change.
"""

import abc
import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

logger = logging.getLogger(__name__)


def normalize_url(url: str) -> str:
    """
    Normalise a URL for consistent dedup comparison.

    - Strips surrounding whitespace and any URL fragment (``#...``).
    - Removes a single trailing slash from the path (but keeps root ``/``).
    - Lower-cases the scheme and host.
    """
    parts = urlsplit(url.strip())
    path = parts.path
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")
    return urlunsplit(
        (parts.scheme.lower(), parts.netloc.lower(), path, parts.query, "")
    )


class BaseVisitedStore(abc.ABC):
    """Interface for a persistent visited-URL registry."""

    @abc.abstractmethod
    def has_visited(self, url: str) -> bool:
        """Return True if *url* has already been scraped."""

    @abc.abstractmethod
    def mark_visited(self, url: str, job_id: str, metadata: dict | None = None) -> None:
        """Record *url* as scraped by *job_id*."""

    @abc.abstractmethod
    def all_visited(self) -> dict:
        """Return a copy of the full registry, keyed by normalised URL."""


class JsonVisitedStore(BaseVisitedStore):
    """
    Thread-safe JSON-file-backed implementation of :class:`BaseVisitedStore`.

    The file is a single JSON object::

        {
            "https://example.com/docs": {
                "job_id": "abc123",
                "scraped_at": "2026-06-12T12:00:00+00:00",
                "metadata": {}
            }
        }
    """

    def __init__(self, path: str | Path):
        self._path = Path(path)
        self._lock = threading.Lock()
        self._data = self._load()
        logger.info(
            "VisitedStore loaded — %d entr(ies) from %s",
            len(self._data),
            self._path,
        )

    def _load(self) -> dict:
        if self._path.exists():
            try:
                return json.loads(self._path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning(
                    "Could not read visited store at %s (%s); starting empty.",
                    self._path,
                    exc,
                )
        return {}

    def _persist(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(self._path.suffix + ".tmp")
        tmp.write_text(json.dumps(self._data, indent=2), encoding="utf-8")
        tmp.replace(self._path)  # atomic on the same filesystem

    def has_visited(self, url: str) -> bool:
        key = normalize_url(url)
        with self._lock:
            return key in self._data

    def mark_visited(self, url: str, job_id: str, metadata: dict | None = None) -> None:
        key = normalize_url(url)
        with self._lock:
            self._data[key] = {
                "job_id": job_id,
                "scraped_at": datetime.now(timezone.utc).isoformat(),
                "metadata": metadata or {},
            }
            self._persist()
        logger.debug("Marked visited: %s (job_id=%s)", key, job_id)

    def all_visited(self) -> dict:
        with self._lock:
            return dict(self._data)


class DynamoDBVisitedStore(BaseVisitedStore):
    """
    DynamoDB-backed implementation of :class:`BaseVisitedStore`.

    Intended for AWS Lambda / multi-instance deployments where a local JSON
    file cannot be shared between invocations. Each scraped URL is one item
    keyed by the normalised URL.

    Table schema
    ------------
    - Partition key: ``url`` (String) \u2014 the normalised URL.
    - Attributes: ``job_id`` (String), ``scraped_at`` (String, ISO-8601),
      ``metadata`` (Map).

    Credentials / region are resolved by boto3 from the environment or the
    Lambda execution role \u2014 nothing is hardcoded here.
    """

    def __init__(self, table_name: str, region_name: str | None = None):
        if not table_name:
            raise ValueError("DynamoDBVisitedStore requires a table_name.")
        import boto3  # imported lazily so JSON-only runs don't need boto3

        self._table_name = table_name
        self._table = boto3.resource(
            "dynamodb", region_name=region_name
        ).Table(table_name)
        logger.info(
            "VisitedStore backend=dynamodb table=%s region=%s",
            table_name,
            region_name or "(default)",
        )

    def has_visited(self, url: str) -> bool:
        key = normalize_url(url)
        resp = self._table.get_item(Key={"url": key})
        return "Item" in resp

    def mark_visited(self, url: str, job_id: str, metadata: dict | None = None) -> None:
        key = normalize_url(url)
        self._table.put_item(
            Item={
                "url": key,
                "job_id": job_id,
                "scraped_at": datetime.now(timezone.utc).isoformat(),
                "metadata": metadata or {},
            }
        )
        logger.debug("Marked visited (dynamodb): %s (job_id=%s)", key, job_id)

    def all_visited(self) -> dict:
        # Full-table scan \u2014 use sparingly; fine for inspection/debugging.
        items: dict = {}
        scan_kwargs: dict = {}
        while True:
            resp = self._table.scan(**scan_kwargs)
            for it in resp.get("Items", []):
                url = it.pop("url")
                items[url] = it
            last_key = resp.get("LastEvaluatedKey")
            if not last_key:
                break
            scan_kwargs["ExclusiveStartKey"] = last_key
        return items


def build_visited_store(settings) -> BaseVisitedStore:
    """
    Construct the visited store selected by configuration.

    Reads from Scrapy ``settings`` (which already merge in environment vars):

    - ``VISITED_STORE_BACKEND``: ``"json"`` (default) or ``"dynamodb"``.
    - JSON backend \u2192 ``VISITED_STORE_PATH``.
    - DynamoDB backend \u2192 ``DYNAMODB_TABLE`` (+ region from the AWS environment).
    """
    backend = (settings.get("VISITED_STORE_BACKEND") or "json").lower()
    if backend == "dynamodb":
        import os

        region = os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION")
        return DynamoDBVisitedStore(
            table_name=settings.get("DYNAMODB_TABLE"),
            region_name=region,
        )
    return JsonVisitedStore(settings.get("VISITED_STORE_PATH", "state/visited.json"))
