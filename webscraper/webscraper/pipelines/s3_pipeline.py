import io
import logging
import os
from urllib.parse import urlparse

from webscraper.items import DocumentItem
from webscraper.pipelines.base_pipeline import BasePipeline

logger = logging.getLogger(__name__)


class S3Pipeline(BasePipeline):
    """
    Upload downloaded documents to an S3 bucket.

    S3 key layout::

        scraped/<hostname>/<job_id>/<filename>

    Configuration (via environment / ``settings.py``)
    --------------------------------------------------
    ``S3_ENABLED``
        Set to ``true`` to activate this pipeline.  Defaults to ``false``.
    ``S3_BUCKET``
        Target bucket name.
    ``AWS_ACCESS_KEY_ID`` / ``AWS_SECRET_ACCESS_KEY`` / ``AWS_DEFAULT_REGION``
        Standard AWS credential env vars (or use an IAM role in Lambda/EC2).

    The pipeline skips gracefully if ``boto3`` is not installed or if
    ``S3_ENABLED`` is ``false``.
    """

    def __init__(self, bucket: str):
        self._bucket = bucket
        self._client = None

    @classmethod
    def from_crawler(cls, crawler):
        bucket = crawler.settings.get("S3_BUCKET", "")
        return cls(bucket=bucket)

    def open_spider(self, spider) -> None:
        super().open_spider(spider)
        try:
            import boto3
            self._client = boto3.client("s3")
            logger.info("S3Pipeline connected — bucket=%s", self._bucket)
        except ImportError:
            logger.warning("boto3 not installed; S3Pipeline will be a no-op.")
            self._client = None

    def process_item(self, item: DocumentItem, spider):
        if not isinstance(item, DocumentItem):
            return item

        if self._client is None or not self._bucket:
            logger.debug(
                "[%s] S3Pipeline skipped (no client or bucket).", item["job_id"]
            )
            return item

        hostname = urlparse(item["url"]).hostname or "unknown"
        s3_key = f"scraped/{hostname}/{item['job_id']}/{item['filename']}"

        try:
            self._client.upload_fileobj(
                io.BytesIO(item["content"]),
                self._bucket,
                s3_key,
                ExtraArgs={"ContentType": _content_type(item["file_type"])},
            )
            logger.info(
                "[%s] Uploaded to S3: s3://%s/%s (%d bytes)",
                item["job_id"],
                self._bucket,
                s3_key,
                item["size_bytes"],
            )
        except Exception as exc:
            logger.error(
                "[%s] S3 upload failed for %s: %s",
                item["job_id"],
                item["filename"],
                exc,
            )

        return item


def _content_type(file_type: str) -> str:
    _MAP = {
        "pdf": "application/pdf",
        "doc": "application/msword",
        "docx": (
            "application/vnd.openxmlformats-officedocument"
            ".wordprocessingml.document"
        ),
    }
    return _MAP.get(file_type.lower(), "application/octet-stream")
