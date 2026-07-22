"""
Classify each downloaded document with the trained Modulhandbuch model.

Where it sits
-------------
Registered in ``settings.ITEM_PIPELINES`` at priority 250 — *after* local storage
(200) so the saved file already exists on disk (its path goes into the review
manifest), and before/around S3 (300). Enabled with ``CLASSIFIER_ENABLED=true``.

What it does
------------
1. On ``open_spider`` it loads the model once per process (shared across the
   concurrent crawl jobs) from ``MODEL_PATH``. If the model or the ``mlclassifier``
   package/dependencies are missing, it logs a warning and becomes a **no-op** —
   the scraper keeps working exactly as before (graceful degradation).
2. For each :class:`DocumentItem` it scores the in-memory bytes (no temp file),
   annotates ``item['extra']['classification']`` with score + decision, and
   appends one line to a per-crawl **review manifest** (JSONL).

The manifest is the bridge to training (spec §14): a human reviews the
``needs_review`` band, then ``python -m mlclassifier ingest --manifest ...``
copies confirmed documents into the labelled set for the next retrain.

Note: scoring runs inline on the reactor thread. Extraction of a very large PDF
briefly blocks other jobs; acceptable at this stage. Moving it to a thread pool
is a future optimisation.
"""

import json
import logging
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

from webscraper.items import DocumentItem
from webscraper.pipelines.base_pipeline import BasePipeline

logger = logging.getLogger(__name__)

# Make the repo-root ``mlclassifier`` package importable when running from the
# webscraper working directory. <repo>/webscraper/webscraper/pipelines/<this>
_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# Where LocalStoragePipeline writes files: <repo>/webscraper/output/<host>/<job>/
_OUTPUT_DIR = Path(__file__).resolve().parents[2] / "output"

# File types the classifier can currently extract. Others are recorded but skipped.
_SUPPORTED_TYPES = {"pdf"}


class ClassificationPipeline(BasePipeline):
    """Score downloaded documents and log them for review / retraining."""

    def __init__(self, model_path: str, manifest_dir: str, s3_enabled: bool, s3_bucket: str):
        self._model_path = model_path
        self._manifest_dir = Path(manifest_dir) if manifest_dir else (_OUTPUT_DIR / "_review")
        self._s3_enabled = s3_enabled
        self._s3_bucket = s3_bucket
        self._clf = None            # loaded classifier, or None when disabled
        self._manifest = None       # open manifest file handle
        self._manifest_path = None
        self._manifest_id = None    # batch/run id the manifest is keyed by

    @classmethod
    def from_crawler(cls, crawler):
        s = crawler.settings
        return cls(
            model_path=s.get("MODEL_PATH", ""),
            manifest_dir=s.get("REVIEW_MANIFEST_DIR", ""),
            s3_enabled=s.getbool("S3_ENABLED", False),
            s3_bucket=s.get("S3_BUCKET", ""),
        )

    # -- lifecycle -------------------------------------------------------------

    def open_spider(self, spider) -> None:
        super().open_spider(spider)
        try:
            from mlclassifier.predict import get_shared_classifier

            self._clf = get_shared_classifier(self._model_path) if self._model_path \
                else get_shared_classifier()
            logger.info(
                "[%s] ClassificationPipeline ready (model_version=%s, thresholds=%s)",
                spider.job_id,
                self._clf.metadata.get("model_version"),
                {"lower": self._clf.lower, "upper": self._clf.upper},
            )
        except Exception as exc:  # noqa: BLE001 — never break the crawl over the model
            logger.warning(
                "[%s] ClassificationPipeline disabled (could not load model): %s",
                spider.job_id, exc,
            )
            self._clf = None
            return

        # Key the manifest by the batch/run id (shared across all URL jobs in a
        # run) so the caller can fetch this run's results. Falls back to the
        # per-spider job_id for standalone spider runs.
        self._manifest_id = os.getenv("SCRAPE_BATCH_ID") or spider.job_id
        self._manifest_dir.mkdir(parents=True, exist_ok=True)
        self._manifest_path = self._manifest_dir / f"manifest_{self._manifest_id}.jsonl"
        # Append: multiple URL jobs in one batch share this file (writes happen
        # on the single reactor thread, so lines don't interleave).
        self._manifest = self._manifest_path.open("a", encoding="utf-8")

    def close_spider(self, spider) -> None:
        super().close_spider(spider)
        if self._manifest is not None:
            self._manifest.close()
            logger.info("[%s] review manifest: %s", spider.job_id, self._manifest_path)
            self._upload_manifest_to_s3(spider)

    def _upload_manifest_to_s3(self, spider) -> None:
        """Publish the manifest to S3 so a remote webapp can read this run's results."""
        if not (self._s3_enabled and self._s3_bucket and self._manifest_path
                and self._manifest_path.exists()):
            return
        key = f"manifests/{self._manifest_id}.jsonl"
        try:
            import boto3

            boto3.client("s3").upload_file(
                str(self._manifest_path), self._s3_bucket, key,
                ExtraArgs={"ContentType": "application/x-ndjson"},
            )
            logger.info("[%s] uploaded manifest → s3://%s/%s",
                        spider.job_id, self._s3_bucket, key)
        except Exception as exc:  # noqa: BLE001 — never fail the crawl over this
            logger.warning("[%s] manifest S3 upload failed: %s", spider.job_id, exc)

    # -- per item --------------------------------------------------------------

    def process_item(self, item, spider):
        if self._clf is None or not isinstance(item, DocumentItem):
            return item

        file_type = (item.get("file_type") or "").lower()
        filename = item.get("filename") or "unknown"
        if file_type not in _SUPPORTED_TYPES:
            spider.crawler.stats.inc_value("webscraper/classify_skipped")
            return item

        try:
            result = self._clf.classify_bytes(item["content"], filename)
        except Exception as exc:  # noqa: BLE001 — a bad file must not kill the crawl
            logger.error("[%s] classify failed for %s: %s", item["job_id"], filename, exc)
            spider.crawler.stats.inc_value("webscraper/classify_error")
            return item

        # Annotate the item so any later pipeline can use the verdict.
        item.setdefault("extra", {})
        item["extra"]["classification"] = result

        self._record_stats(spider, result)
        self._write_manifest(item, result)

        logger.info(
            "[%s] %s → %s (score=%s) %s",
            item["job_id"], filename, result["decision"],
            result["module_handbook_score"], result["extraction_status"],
        )
        return item

    # -- helpers ---------------------------------------------------------------

    def _record_stats(self, spider, result: dict) -> None:
        stats = spider.crawler.stats
        stats.inc_value("webscraper/classified")
        mapping = {
            "automatic_positive": "webscraper/classify_positive",
            "automatic_negative": "webscraper/classify_negative",
            "needs_review": "webscraper/classify_review",
        }
        key = mapping.get(result["decision"])
        if key:
            stats.inc_value(key)

    def _write_manifest(self, item, result: dict) -> None:
        if self._manifest is None:
            return
        hostname = urlparse(item["url"]).hostname or "unknown"
        # Path LocalStoragePipeline saves to (best-effort; may be absent in S3-only mode).
        saved_path = _OUTPUT_DIR / hostname / item["job_id"] / item["filename"]
        # Key S3Pipeline uploads to: scraped/<host>/<job>/<filename>.
        s3_key = f"scraped/{hostname}/{item['job_id']}/{item['filename']}"
        entry = {
            "job_id": item["job_id"],
            "url": item["url"],
            "source_page": item.get("source_page", ""),
            "hostname": hostname,
            "filename": item["filename"],
            "file_type": item.get("file_type", ""),
            "saved_path": str(saved_path),
            "s3_key": s3_key if self._s3_enabled else "",
            "module_handbook_score": result["module_handbook_score"],
            "decision": result["decision"],
            "is_module_handbook": result["is_module_handbook"],
            "extraction_status": result["extraction_status"],
            "model_version": result["model_version"],
            "crawled_at": item.get("crawled_at", ""),
        }
        self._manifest.write(json.dumps(entry, ensure_ascii=False) + "\n")
        self._manifest.flush()
