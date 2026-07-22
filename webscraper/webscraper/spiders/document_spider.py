import logging
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

import scrapy
from scrapy.http import TextResponse

from webscraper.items import DocumentItem
from webscraper.spiders.base_spider import BaseSpider

logger = logging.getLogger(__name__)

# Default file extensions this spider targets if none are supplied.
TARGET_EXTENSIONS = {".pdf", ".doc", ".docx"}

# Extensions that are never worth following as HTML pages (assets / media).
_NON_PAGE_EXTENSIONS = {
    ".css", ".js", ".json", ".xml", ".rss", ".zip", ".gz", ".tar", ".rar",
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".bmp", ".ico", ".tiff",
    ".mp3", ".mp4", ".avi", ".mov", ".mkv", ".webm", ".wav", ".flac", ".ogg",
    ".woff", ".woff2", ".ttf", ".eot",
}

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

# Bounded-crawl defaults (overridable via settings / env — see settings.py).
DEFAULT_MAX_DEPTH = 2
DEFAULT_MAX_PAGES = 60


def _normalize_extensions(file_types) -> set:
    """Normalise a list like ['pdf', '.PNG'] into {'.pdf', '.png'}."""
    normalized = set()
    for ft in file_types or []:
        ft = str(ft).strip().lower()
        if not ft:
            continue
        normalized.add(ft if ft.startswith(".") else "." + ft)
    return normalized


def _base_domain(hostname: str) -> str:
    """Registrable-ish base domain: the last two labels (e.g. ``fh-aachen.de``)."""
    if not hostname:
        return ""
    labels = hostname.lower().split(".")
    return ".".join(labels[-2:]) if len(labels) >= 2 else hostname.lower()


class DocumentSpider(BaseSpider):
    """
    Crawl a seed URL (and, up to a bounded depth, its same-site pages) and
    download all linked PDF / Word documents.

    Bounded deep crawl
    ------------------
    University document pages (e.g. Modulhandbücher) are rarely linked from the
    homepage directly, so the spider follows **same-site** HTML links up to
    ``CRAWL_MAX_DEPTH`` levels, visiting at most ``CRAWL_MAX_PAGES`` pages per
    seed. Both are configurable and default to small, polite values. Documents
    found on any visited page are downloaded; the per-run download cap
    (``CLOSESPIDER_ITEMCOUNT``) still applies as a backstop.

    Usage (via run.py)
    ------------------
    ``python run.py https://example.edu``

    Extending
    ---------
    Override ``_is_target_url`` to widen / narrow the set of downloaded links, or
    ``_should_follow`` to change which pages are crawled.
    """

    name = "document"

    def __init__(self, start_url: str, *args, file_types=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.start_urls = [start_url]
        self.target_extensions = _normalize_extensions(file_types) or set(
            TARGET_EXTENSIONS
        )
        self._seed_domain = _base_domain(urlparse(start_url).hostname or "")
        # Scrapy's OffsiteMiddleware filters requests outside these domains
        # (subdomains allowed). Belt to the explicit _same_site() checks below.
        if self._seed_domain:
            self.allowed_domains = [self._seed_domain]
        self._pages_crawled = 0
        # Limits are read lazily from settings on first parse (settings aren't
        # attached to the spider until after __init__).
        self._max_depth = None
        self._max_pages = None
        logger.info(
            "[%s] DocumentSpider targeting: %s  extensions=%s  domain=%s",
            self.job_id, start_url, sorted(self.target_extensions), self._seed_domain,
        )

    def _init_limits(self) -> None:
        if self._max_depth is not None:
            return
        s = getattr(self, "settings", None)
        self._max_depth = s.getint("CRAWL_MAX_DEPTH", DEFAULT_MAX_DEPTH) if s else DEFAULT_MAX_DEPTH
        self._max_pages = s.getint("CRAWL_MAX_PAGES", DEFAULT_MAX_PAGES) if s else DEFAULT_MAX_PAGES
        logger.info(
            "[%s] crawl limits — max_depth=%d max_pages=%d",
            self.job_id, self._max_depth, self._max_pages,
        )

    def parse(self, response, depth: int = 0, **kwargs):
        """Parse a page: download found documents, then follow same-site links."""
        self._init_limits()
        self._pages_crawled += 1
        page_url = response.url
        logger.info(
            "[%s] Parsing page (depth=%d, #%d): %s",
            self.job_id, depth, self._pages_crawled, page_url,
        )

        # Non-HTML responses (e.g. a followed link that turned out binary) can't
        # be scanned for links — skip gracefully.
        if not isinstance(response, TextResponse):
            return

        candidates = set()
        for selector in _LINK_SELECTORS:
            for href in response.css(selector).getall():
                if href and href.strip():
                    candidates.add(urljoin(page_url, href.strip()))

        found = 0
        page_links = []
        for absolute_url in candidates:
            if self._is_target_url(absolute_url):
                # Only download documents hosted on the same site (spec: uni
                # Modulhandbücher live on the university's own domain).
                if not self._same_site(absolute_url):
                    continue
                found += 1
                self.crawler.stats.inc_value("webscraper/files_found")
                yield scrapy.Request(
                    url=absolute_url,
                    callback=self._download_document,
                    cb_kwargs={"source_page": page_url},
                    errback=self._on_error,
                )
            elif self._should_follow(absolute_url):
                page_links.append(absolute_url)

        logger.info(
            "[%s] depth=%d: queued %d document(s), %d follow candidate(s) from %s",
            self.job_id, depth, found, len(page_links), page_url,
        )

        # Follow same-site pages until the depth / page budget is spent.
        if depth < self._max_depth:
            for link in page_links:
                if self._pages_crawled >= self._max_pages:
                    logger.info(
                        "[%s] page budget (%d) reached — not following further.",
                        self.job_id, self._max_pages,
                    )
                    break
                yield scrapy.Request(
                    url=link,
                    callback=self.parse,
                    cb_kwargs={"depth": depth + 1},
                    errback=self._on_error,
                )

    def _download_document(self, response, source_page: str):
        """Receive a binary document response and yield a DocumentItem."""
        url = response.url
        filename = urlparse(url).path.split("/")[-1] or "unknown"
        extension = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        content = response.body

        logger.info(
            "[%s] Downloaded %s (%d bytes) from %s",
            self.job_id, filename, len(content), source_page,
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
            self.job_id, failure.request.url, repr(failure.value),
        )

    def _is_target_url(self, url: str) -> bool:
        """Return True if *url* ends with one of the target extensions."""
        path = urlparse(url).path.lower()
        return any(path.endswith(ext) for ext in self.target_extensions)

    def _same_site(self, url: str) -> bool:
        """True if *url* is http(s) on the seed's base domain (subdomains ok)."""
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False
        return _base_domain(parsed.hostname or "") == self._seed_domain

    def _should_follow(self, url: str) -> bool:
        """Follow only same-site http(s) pages that aren't assets/documents."""
        if not self._same_site(url):
            return False
        path = urlparse(url).path.lower()
        ext = "." + path.rsplit(".", 1)[-1] if "." in path.rsplit("/", 1)[-1] else ""
        return ext not in _NON_PAGE_EXTENSIONS
