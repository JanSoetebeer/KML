import gzip
import logging
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

import scrapy
from scrapy import Selector
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

# HTML attributes scanned for downloadable links (documents, images, media).
# Anchors (<a>) are handled separately so their link text can feed the
# relevance score — see parse().
_ASSET_SELECTORS = (
    "link::attr(href)",
    "img::attr(src)",
    "source::attr(src)",
    "audio::attr(src)",
    "video::attr(src)",
)

# Bounded-crawl defaults (overridable via settings / env — see settings.py).
DEFAULT_MAX_DEPTH = 2
DEFAULT_MAX_PAGES = 60

# ---------------------------------------------------------------------------
# Focused-crawl relevance scoring
#
# The crawl budget (CRAWL_MAX_PAGES) is small, so *which* pages we spend it on
# matters far more than how many. Each candidate link is scored from tokens in
# its URL and anchor text; the score becomes the Scrapy request priority, so the
# frontier is explored best-first — pages that look like they lead to
# Modulhandbücher are visited before news/events/imprint pages. Documents are
# always fetched (they don't consume the page budget).
# ---------------------------------------------------------------------------

_POSITIVE_TOKENS = {
    "modulhandbuch": 100, "modulhandbuecher": 100, "module-handbook": 100,
    "modulbeschreibung": 60, "modulkatalog": 60,
    "modul": 25, "module": 20,
    "pruefungsordnung": 35, "studienordnung": 35, "studienplan": 30,
    "curriculum": 30, "ordnung": 12,
    "studiengang": 20, "studiengaenge": 20, "studium": 15, "studies": 10,
    "bachelor": 15, "master": 15, "b-sc": 10, "m-sc": 10,
    "vorlesungsverzeichnis": 20, "lehrveranstaltung": 12, "lehre": 8,
    "fachbereich": 8, "fakultaet": 8, "institut": 5,
    "download": 10, "downloads": 10, "dokumente": 10, "formulare": 6,
    "pdf": 4,
}

_NEGATIVE_TOKENS = {
    "aktuelles": -40, "news": -40, "presse": -40, "pressemitteilung": -40,
    "veranstaltung": -30, "event": -30, "termine": -20, "kalender": -20,
    "kontakt": -30, "impressum": -60, "datenschutz": -60, "cookie": -50,
    "mensa": -30, "wohnen": -20, "sport": -20, "hochschulsport": -25,
    "stellenangebot": -30, "karriere": -20, "jobs": -20, "stellen": -20,
    "login": -40, "anmeldung": -20, "suche": -25, "search": -25,
    "sitemap": -20, "rss": -25, "feed": -25,
    "english": -15, "/en/": -15,
    "alumni": -20, "spende": -25, "blog": -20, "gremien": -20,
}

# Umlaut / ß folding so anchor text like "Modulhandbücher" and
# "Prüfungsordnung" matches the ASCII tokens above.
_FOLD_MAP = str.maketrans({
    "ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss",
    "Ä": "ae", "Ö": "oe", "Ü": "ue",
})

# Priority floor guaranteeing documents are scheduled before any page follow.
_DOCUMENT_BASE_PRIORITY = 1000


def _fold(text: str) -> str:
    """Lowercase and fold German umlauts/ß for keyword matching."""
    if not text:
        return ""
    return text.translate(_FOLD_MAP).lower()


def _keyword_score(url: str, anchor_text: str = "") -> int:
    """Relevance score for a link from tokens in its URL + anchor text."""
    hay = _fold(url) + " ␟ " + _fold(anchor_text)
    score = 0
    for token, weight in _POSITIVE_TOKENS.items():
        if token in hay:
            score += weight
    for token, weight in _NEGATIVE_TOKENS.items():
        if token in hay:
            score += weight
    return score


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


def _sitemap_locs(response) -> tuple[list, bool]:
    """
    Extract ``<loc>`` values from a sitemap response (handling gzipped bodies
    and XML namespaces), and report whether it is a sitemap *index*.

    Returns ``(locs, is_index)``.
    """
    body = response.body or b""
    if response.url.endswith(".gz") or body[:2] == b"\x1f\x8b":
        try:
            body = gzip.decompress(body)
        except OSError:
            pass
    is_index = b"<sitemapindex" in body[:5000].lower()
    # local-name() sidesteps the sitemap XML namespace.
    locs = Selector(body=body, type="xml").xpath(
        "//*[local-name()='loc']/text()"
    ).getall()
    return locs, is_index


class DocumentSpider(BaseSpider):
    """
    Crawl a seed URL (and, up to a bounded depth, its same-site pages) and
    download all linked PDF / Word documents.

    Focused (best-first) crawl
    --------------------------
    University document pages (e.g. Modulhandbücher) are rarely linked from the
    homepage directly, and the page budget (``CRAWL_MAX_PAGES``) is small, so the
    order in which pages are visited is critical. Every candidate link is scored
    by keyword tokens in its URL and anchor text (see ``_keyword_score``) and the
    score is used as the Scrapy request **priority** — the frontier is explored
    best-first, so ``/studium/.../modulhandbuch`` pages are reached before
    news/events/imprint pages that would otherwise burn the budget.

    Sitemap seeding
    ---------------
    Before falling back to link traversal, the spider fetches ``/sitemap.xml``
    (and any sitemaps declared in ``robots.txt``). Sitemaps are a flat index of
    the whole site: matching document URLs are downloaded directly and
    high-scoring pages are seeded near the top of the frontier — skipping the
    depth traversal for the pages that matter most. Controlled by
    ``CRAWL_USE_SITEMAP`` (default on).

    Usage (via run.py)
    ------------------
    ``python run.py https://example.edu``

    Extending
    ---------
    Override ``_is_target_url`` to widen / narrow the set of downloaded links,
    ``_should_follow`` to change which pages are crawled, or the
    ``_POSITIVE_TOKENS`` / ``_NEGATIVE_TOKENS`` maps to retune relevance.
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
        # Limits are read lazily from settings on first use (settings aren't
        # attached to the spider until after __init__).
        self._max_depth = None
        self._max_pages = None
        self._use_sitemap = None
        self._max_sitemap_urls = None
        self._max_child_sitemaps = None
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
        self._use_sitemap = s.getbool("CRAWL_USE_SITEMAP", True) if s else True
        self._max_sitemap_urls = s.getint("CRAWL_MAX_SITEMAP_URLS", 50) if s else 50
        self._max_child_sitemaps = s.getint("CRAWL_MAX_CHILD_SITEMAPS", 10) if s else 10
        logger.info(
            "[%s] crawl limits — max_depth=%d max_pages=%d sitemap=%s",
            self.job_id, self._max_depth, self._max_pages, self._use_sitemap,
        )

    def start_requests(self):
        """Seed the crawl: the start URL, plus sitemap discovery (if enabled)."""
        self._init_limits()
        seed = self.start_urls[0]
        yield scrapy.Request(
            seed, callback=self.parse, cb_kwargs={"depth": 0}, errback=self._on_error,
        )

        if not self._use_sitemap:
            return
        parsed = urlparse(seed)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        # /sitemap.xml is the near-universal default; robots.txt may declare more.
        yield scrapy.Request(
            f"{origin}/sitemap.xml", callback=self._parse_sitemap,
            cb_kwargs={"sitemap_depth": 0}, errback=self._on_sitemap_error,
            priority=60, dont_filter=True,
        )
        yield scrapy.Request(
            f"{origin}/robots.txt", callback=self._parse_robots_for_sitemaps,
            errback=self._on_sitemap_error, priority=60, dont_filter=True,
        )

    def parse(self, response, depth: int = 0, **kwargs):
        """Parse a page: download found documents, then follow same-site links."""
        self._init_limits()
        # Best-first scheduling can queue more pages than the budget allows;
        # drop any that arrive once the budget is spent (documents still flow
        # through _download_document, which is unaffected by the page budget).
        if self._pages_crawled >= self._max_pages:
            return
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

        # Collect candidates as url -> anchor text (asset selectors have none).
        candidates: dict[str, str] = {}
        for anchor in response.css("a"):
            href = anchor.attrib.get("href")
            if not href or not href.strip():
                continue
            absolute_url = urljoin(page_url, href.strip())
            text = " ".join(t.strip() for t in anchor.css("::text").getall() if t.strip())
            # Prefer the most descriptive anchor text seen for this URL.
            if len(text) > len(candidates.get(absolute_url, "")):
                candidates[absolute_url] = text
        for selector in _ASSET_SELECTORS:
            for href in response.css(selector).getall():
                if href and href.strip():
                    candidates.setdefault(urljoin(page_url, href.strip()), "")

        found = 0
        page_links = []  # (score, url) for same-site follow candidates
        for absolute_url, anchor_text in candidates.items():
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
                    priority=_DOCUMENT_BASE_PRIORITY + _keyword_score(absolute_url, anchor_text),
                    errback=self._on_error,
                )
            elif self._should_follow(absolute_url):
                page_links.append((_keyword_score(absolute_url, anchor_text), absolute_url))

        logger.info(
            "[%s] depth=%d: queued %d document(s), %d follow candidate(s) from %s",
            self.job_id, depth, found, len(page_links), page_url,
        )

        # Follow same-site pages best-first (highest score first) until the
        # depth / page budget is spent.
        if depth < self._max_depth:
            page_links.sort(key=lambda t: t[0], reverse=True)
            for score, link in page_links:
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
                    priority=score,
                    errback=self._on_error,
                )

    def _parse_sitemap(self, response, sitemap_depth: int = 0):
        """
        Parse a sitemap (or sitemap index): download matching documents directly
        and seed high-scoring pages near the top of the frontier.
        """
        self._init_limits()
        locs, is_index = _sitemap_locs(response)
        if not locs:
            return

        if is_index:
            # Recurse into child sitemaps, most-relevant first, bounded in both
            # breadth (_max_child_sitemaps) and depth (2 levels).
            if sitemap_depth >= 2:
                return
            children = sorted(
                (u.strip() for u in locs if u.strip()),
                key=_keyword_score, reverse=True,
            )
            for child in children[: self._max_child_sitemaps]:
                yield scrapy.Request(
                    child, callback=self._parse_sitemap,
                    cb_kwargs={"sitemap_depth": sitemap_depth + 1},
                    errback=self._on_sitemap_error, priority=50, dont_filter=True,
                )
            return

        scored_pages = []
        docs = 0
        for loc in locs:
            url = loc.strip()
            if not url or not self._same_site(url):
                continue
            if self._is_target_url(url):
                docs += 1
                self.crawler.stats.inc_value("webscraper/files_found")
                yield scrapy.Request(
                    url=url, callback=self._download_document,
                    cb_kwargs={"source_page": response.url},
                    priority=_DOCUMENT_BASE_PRIORITY + _keyword_score(url),
                    errback=self._on_error,
                )
                continue
            score = _keyword_score(url)
            if score > 0:
                scored_pages.append((score, url))

        scored_pages.sort(key=lambda t: t[0], reverse=True)
        seeded = scored_pages[: self._max_sitemap_urls]
        logger.info(
            "[%s] sitemap %s → %d document(s), %d page(s) seeded (of %d relevant)",
            self.job_id, response.url, docs, len(seeded), len(scored_pages),
        )
        # Seed sitemap hub pages shallow: they are already deep in the site, so
        # allow at most one more level of link-following from them.
        seed_depth = max(0, self._max_depth - 1)
        for score, url in seeded:
            yield scrapy.Request(
                url=url, callback=self.parse,
                cb_kwargs={"depth": seed_depth},
                priority=score, errback=self._on_error,
            )

    def _parse_robots_for_sitemaps(self, response):
        """Follow any ``Sitemap:`` directives declared in robots.txt."""
        if not isinstance(response, TextResponse):
            return
        for line in response.text.splitlines():
            if line.lower().startswith("sitemap:"):
                sitemap_url = line.split(":", 1)[1].strip()
                if sitemap_url:
                    yield scrapy.Request(
                        sitemap_url, callback=self._parse_sitemap,
                        cb_kwargs={"sitemap_depth": 0},
                        errback=self._on_sitemap_error, priority=50,
                        dont_filter=True,
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

    def _on_sitemap_error(self, failure):
        # Sitemaps are best-effort discovery; a missing /sitemap.xml or
        # robots.txt is expected and must not derail the seed crawl.
        logger.debug(
            "[%s] Sitemap discovery skipped for %s — %s",
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
