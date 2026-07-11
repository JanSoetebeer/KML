import logging
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

import scrapy

from webscraper.items import DocumentItem
from webscraper.spiders.base_spider import BaseSpider

logger = logging.getLogger(__name__)

# Default file extensions this spider targets if none are supplied.
TARGET_EXTENSIONS = {".pdf", ".doc", ".docx"}

# HTML attributes scanned for downloadable links (covers documents, images and
# media). Each is a CSS selector returning a URL-bearing attribute.
_LINK_SELECTORS = (
    "a::attr(href)",
    "link::attr(href)",
    "img::attr(src)",
    "source::attr(src)",
    "audio::attr(src)",
    "video::attr(src)",
)


def _normalize_extensions(file_types) -> set:
    """Normalise a list like ['pdf', '.PNG'] into {'.pdf', '.png'}."""
    normalized = set()
    for ft in file_types or []:
        ft = str(ft).strip().lower()
        if not ft:
            continue
        normalized.add(ft if ft.startswith(".") else "." + ft)
    return normalized


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

    def __init__(self, start_url: str, *args, file_types=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.start_urls = [start_url]
        self.target_extensions = _normalize_extensions(file_types) or set(
            TARGET_EXTENSIONS
        )
        logger.info(
            "[%s] DocumentSpider targeting: %s  extensions=%s",
            self.job_id,
            start_url,
            sorted(self.target_extensions),
        )

    def parse(self, response, **kwargs):
        """
        Parse the seed page and yield download requests for found documents.
        """
        page_url = response.url
        logger.info("[%s] Parsing page: %s", self.job_id, page_url)

        candidates = set()
        for selector in _LINK_SELECTORS:
            for href in response.css(selector).getall():
                if href and href.strip():
                    candidates.add(urljoin(page_url, href.strip()))
        logger.debug(
            "[%s] Found %d candidate link(s) on %s",
            self.job_id,
            len(candidates),
            page_url,
        )

        found = 0
        for absolute_url in candidates:
            if self._is_target_url(absolute_url):
                found += 1
                self.crawler.stats.inc_value("webscraper/files_found")
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
        self.crawler.stats.inc_value("webscraper/files_downloaded")
        self.crawler.stats.inc_value("webscraper/bytes_downloaded", len(content))

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

    def _is_target_url(self, url: str) -> bool:
        """Return True if *url* ends with one of the target extensions."""
        path = urlparse(url).path.lower()
        return any(path.endswith(ext) for ext in self.target_extensions)
