import logging
import os
from pathlib import Path
from urllib.parse import urlparse

from webscraper.items import DocumentItem
from webscraper.pipelines.base_pipeline import BasePipeline

logger = logging.getLogger(__name__)

_OUTPUT_DIR = Path(__file__).resolve().parents[2] / "output"


class LocalStoragePipeline(BasePipeline):
    """
    Save downloaded documents to the local filesystem.

    Directory layout::

        output/
        └── <hostname>/
            └── <job_id>/
                └── report.pdf

    Enabled via ``LOCAL_ENABLED=true`` in settings (default: on).
    """

    def open_spider(self, spider) -> None:
        super().open_spider(spider)
        _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    def process_item(self, item: DocumentItem, spider):
        if not isinstance(item, DocumentItem):
            return item

        hostname = urlparse(item["url"]).hostname or "unknown"
        dest_dir = _OUTPUT_DIR / hostname / item["job_id"]
        dest_dir.mkdir(parents=True, exist_ok=True)

        dest_file = dest_dir / item["filename"]

        try:
            dest_file.write_bytes(item["content"])
            logger.info(
                "[%s] Saved locally: %s (%d bytes)",
                item["job_id"],
                dest_file,
                item["size_bytes"],
            )
        except OSError as exc:
            logger.error(
                "[%s] Failed to save %s locally: %s",
                item["job_id"],
                item["filename"],
                exc,
            )

        return item
