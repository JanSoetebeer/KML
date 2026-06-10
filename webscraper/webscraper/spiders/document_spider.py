import logging
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

import scrapy

from webscraper.items import DocumentItem
from webscraper.spiders.base_spider import BaseSpider

logger = logging.getLogger(__name__)

# File extensions this spider targets
TARGET_EXTENSIONS = {".pdf", ".doc", ".docx"}


class DocumentSpider(BaseSpider):
    """
    Crawl a single seed URL and download all linked PDF / Word documents.

    Usage (via run.py)
    ------------------
    ``python run.py https://example.com/resources``

    How it works
    ------------
    1. Fetch the seed page.
    2. Scan every ``<a href>`` for links whose path ends in a target extension.
    3. Yield a Scrapy ``Request`` for each document URL.
    4. On receiving the binary response, populate a :class:`~webscraper.items.DocumentItem`
       and yield it to the pipeline.

    Extending
    ---------
    Override ``_is_target_url`` to widen / narrow the set of crawled links
    without touching the rest of the spider logic.
    """

    name = "document"

    def __init__(self, start_url: str, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.start_urls = [start_url]
        logger.info("[%s] DocumentSpider targeting: %s", self.job_id, start_url)

    def parse(self, response, **kwargs):
        """
        Parse the seed page and yield download requests for found documents.
        """
        page_url = response.url
        logger.info("[%s] Parsing page: %s", self.job_id, page_url)

        links = response.css("a::attr(href)").getall()
        logger.debug("[%s] Found %d raw links on %s", self.job_id, len(links), page_url)

        found = 0
        for href in links:
            absolute_url = urljoin(page_url, href.strip())
            if self._is_target_url(absolute_url):
                found += 1
                logger.debug("[%s] Queuing document: %s", self.job_id, absolute_url)
                yield scrapy.Request(
                    url=absolute_url,
                    callback=self._download_document,
                    cb_kwargs={"source_page": page_url},
                    errback=self._on_error,
                )

        logger.info(
            "[%s] Queued %d document(s) from %s", self.job_id, found, page_url
        )

    def _download_document(self, response, source_page: str):
        """Receive a binary document response and yield a DocumentItem."""
        url = response.url
        filename = urlparse(url).path.split("/")[-1] or "unknown"
        extension = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        content = response.body

        logger.info(
            "[%s] Downloaded %s (%d bytes) from %s",
            self.job_id,
            filename,
            len(content),
            source_page,
        )

        yield DocumentItem(
            url=url,
            filename=filename,
            source_page=source_page,
            file_type=extension.lstrip("."),
            content=content,
            size_bytes=len(content),
            crawled_at=datetime.now(timezone.utc).isoformat(),
            job_id=self.job_id,
            extra={},
        )

    def _on_error(self, failure):
        logger.error(
            "[%s] Request failed: %s — %s",
            self.job_id,
            failure.request.url,
            repr(failure.value),
        )

    @staticmethod
    def _is_target_url(url: str) -> bool:
        """Return True if *url* ends with one of the target extensions."""
        path = urlparse(url).path.lower()
        return any(path.endswith(ext) for ext in TARGET_EXTENSIONS)
