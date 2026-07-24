import gzip
import logging
from urllib.parse import urljoin, urlparse

import scrapy
from scrapy import Selector
from scrapy.http import TextResponse

from webscraper.profiles import get_profile
from webscraper.spiders.base_spider import BaseSpider

logger = logging.getLogger(__name__)

# Extensions that are never worth following as HTML pages (assets / media /
# documents). Document extensions are included so profiles that don't *target*
# them (e.g. an HTML-content profile) never waste a fetch following them as a
# page — document-harvesting profiles still download them via ``is_target``,
# which is checked before ``_should_follow``.
_NON_PAGE_EXTENSIONS = {
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".odt", ".rtf",
    ".css", ".js", ".json", ".xml", ".rss", ".zip", ".gz", ".tar", ".rar",
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".bmp", ".ico", ".tiff",
    ".mp3", ".mp4", ".avi", ".mov", ".mkv", ".webm", ".wav", ".flac", ".ogg",
    ".woff", ".woff2", ".ttf", ".eot",
}

# HTML attributes scanned for downloadable links (documents, images, media).
# Anchors (<a>) are handled separately so their link text can feed the
# profile's relevance score — see parse().
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

# Priority floor guaranteeing target resources are scheduled before page follows.
_DOCUMENT_BASE_PRIORITY = 1000

# Extra priority for a link that hops into a not-yet-seen faculty subdomain
# (e.g. tu-dortmund.de → cs.tu-dortmund.de). University documents frequently
# live on these faculty sites, so crossing into one is worth exploring promptly.
_CROSS_SUBDOMAIN_BOOST = 50


def _normalize_extensions(file_types) -> frozenset:
    """Normalise a list like ['pdf', '.PNG'] into {'.pdf', '.png'}."""
    normalized = set()
    for ft in file_types or []:
        ft = str(ft).strip().lower()
        if not ft:
            continue
        normalized.add(ft if ft.startswith(".") else "." + ft)
    return frozenset(normalized)


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
    Generic crawl **engine**: fetch a seed URL and its same-site pages up to a
    bounded depth, delegating every use-case-specific decision to a pluggable
    :class:`~webscraper.profiles.base.ExtractionProfile`.

    What the engine owns (generic, unchanged per use case)
    ------------------------------------------------------
    * **Best-first (focused) crawl.** Each candidate link is scored by the active
      profile (``score_link``) and that score becomes the Scrapy request
      *priority*, so the frontier is explored best-first within ``CRAWL_MAX_PAGES``.
    * **Sitemap seeding.** ``/sitemap.xml`` (+ robots.txt-declared sitemaps) is
      fetched first: matching target resources are downloaded directly and
      high-scoring pages are seeded near the top of the frontier.
    * **Faculty-subdomain discovery.** A link hopping into a new same-base-domain
      subdomain (e.g. ``cs.tu-dortmund.de``) gets a fresh depth budget + a
      priority boost and its own sitemap fetch — that's the main-site-to-faculty
      jump where university documents often live.
    * Same-site rules, depth/page budgets, dedup, stats.

    What the profile owns (swap per use case, no engine changes)
    ------------------------------------------------------------
    * ``score_link``    — frontier priority (keyword steering, etc.).
    * ``is_target``     — which links are resources to fetch and extract.
    * ``extract_target``— fetched binary resource → item(s) (document harvesting).
    * ``extract_page``  — fetched HTML page → item(s) (content / structured needs).

    Select the profile by name via ``CRAWL_PROFILE`` / ``--profile`` / the
    ``profile=`` spider argument (default: ``modulhandbuch``).

    Usage (via run.py)
    ------------------
    ``python run.py https://example.edu --profile modulhandbuch``
    """

    name = "document"

    def __init__(self, start_url: str, *args, file_types=None, profile=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.start_urls = [start_url]
        self.profile = get_profile(profile)
        # A ``file_types`` override widens/narrows what the profile downloads
        # without changing its scoring — one source of truth for targets.
        override = _normalize_extensions(file_types)
        if override:
            self.profile.target_extensions = override
        self._seed_domain = _base_domain(urlparse(start_url).hostname or "")
        # Scrapy's OffsiteMiddleware filters requests outside these domains
        # (subdomains allowed). Belt to the explicit _same_site() checks below.
        if self._seed_domain:
            self.allowed_domains = [self._seed_domain]
        self._pages_crawled = 0
        # Subdomains whose sitemap we've already fetched (seed + discovered
        # faculty subdomains), so each is discovered at most once.
        self._sitemapped_subdomains: set[str] = set()
        # Limits are read lazily from settings on first use (settings aren't
        # attached to the spider until after __init__).
        self._max_depth = None
        self._max_pages = None
        self._use_sitemap = None
        self._max_sitemap_urls = None
        self._max_child_sitemaps = None
        self._max_subdomain_sitemaps = None
        logger.info(
            "[%s] DocumentSpider — seed=%s profile=%s targets=%s domain=%s",
            self.job_id, start_url, self.profile.name,
            sorted(self.profile.target_extensions), self._seed_domain,
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
        self._max_subdomain_sitemaps = s.getint("CRAWL_MAX_SUBDOMAIN_SITEMAPS", 15) if s else 15
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
        self._sitemapped_subdomains.add(parsed.netloc)
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

    def _discover_subdomain(self, url: str):
        """
        Fetch the sitemap of a newly-seen (faculty) subdomain, once per
        subdomain and bounded by ``CRAWL_MAX_SUBDOMAIN_SITEMAPS``. University
        documents commonly live on faculty subdomains that the main site's
        sitemap doesn't list, so each such subdomain gets its own discovery.
        """
        if not self._use_sitemap:
            return
        parsed = urlparse(url)
        host = parsed.netloc
        if not host or host in self._sitemapped_subdomains:
            return
        if len(self._sitemapped_subdomains) >= self._max_subdomain_sitemaps:
            return
        self._sitemapped_subdomains.add(host)
        origin = f"{parsed.scheme or 'https'}://{host}"
        logger.info("[%s] discovered faculty subdomain — fetching %s/sitemap.xml",
                    self.job_id, origin)
        yield scrapy.Request(
            f"{origin}/sitemap.xml", callback=self._parse_sitemap,
            cb_kwargs={"sitemap_depth": 0}, errback=self._on_sitemap_error,
            priority=55, dont_filter=True,
        )

    def parse(self, response, depth: int = 0, **kwargs):
        """Parse a page: extract from it, fetch target resources, follow links."""
        self._init_limits()
        # Best-first scheduling can queue more pages than the budget allows;
        # drop any that arrive once the budget is spent (target fetches still
        # flow through _fetch_target, which is unaffected by the page budget).
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

        # Let the profile extract item(s) from the page itself (HTML-content /
        # structured-field needs). Document-harvesting profiles yield nothing here.
        yield from self.profile.extract_page(response, self)

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
            if self.profile.is_target(absolute_url, anchor_text):
                # Only fetch resources hosted on the same site (spec: uni
                # documents live on the university's own domain).
                if not self._same_site(absolute_url):
                    continue
                found += 1
                self.crawler.stats.inc_value("webscraper/files_found")
                yield scrapy.Request(
                    url=absolute_url,
                    callback=self._fetch_target,
                    cb_kwargs={"source_page": page_url},
                    priority=_DOCUMENT_BASE_PRIORITY + self.profile.score_link(absolute_url, anchor_text),
                    errback=self._on_error,
                )
            elif self._should_follow(absolute_url):
                page_links.append((self.profile.score_link(absolute_url, anchor_text), absolute_url))

        logger.info(
            "[%s] depth=%d: queued %d target(s), %d follow candidate(s) from %s",
            self.job_id, depth, found, len(page_links), page_url,
        )

        # Follow same-site pages best-first (highest score first) until the
        # page budget is spent. A link that hops into a *new* faculty subdomain
        # gets a fresh depth budget (depth=0) and a priority boost — that jump
        # must not be cut off by the shallow same-subdomain depth cap.
        page_links.sort(key=lambda t: t[0], reverse=True)
        current_subdomain = urlparse(page_url).netloc
        for score, link in page_links:
            if self._pages_crawled >= self._max_pages:
                logger.info(
                    "[%s] page budget (%d) reached — not following further.",
                    self.job_id, self._max_pages,
                )
                break
            crosses_subdomain = urlparse(link).netloc != current_subdomain and score > 0
            if crosses_subdomain:
                yield from self._discover_subdomain(link)
                next_depth, priority = 0, score + _CROSS_SUBDOMAIN_BOOST
            elif depth < self._max_depth:
                next_depth, priority = depth + 1, score
            else:
                continue  # at depth cap and not a faculty hop — stop here
            yield scrapy.Request(
                url=link,
                callback=self.parse,
                cb_kwargs={"depth": next_depth},
                priority=priority,
                errback=self._on_error,
            )

    def _parse_sitemap(self, response, sitemap_depth: int = 0):
        """
        Parse a sitemap (or sitemap index): fetch matching target resources
        directly and seed high-scoring pages near the top of the frontier.
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
                key=self.profile.score_link, reverse=True,
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
            if self.profile.is_target(url):
                docs += 1
                self.crawler.stats.inc_value("webscraper/files_found")
                yield scrapy.Request(
                    url=url, callback=self._fetch_target,
                    cb_kwargs={"source_page": response.url},
                    priority=_DOCUMENT_BASE_PRIORITY + self.profile.score_link(url),
                    errback=self._on_error,
                )
                continue
            score = self.profile.score_link(url)
            if score > 0:
                scored_pages.append((score, url))

        scored_pages.sort(key=lambda t: t[0], reverse=True)
        seeded = scored_pages[: self._max_sitemap_urls]
        logger.info(
            "[%s] sitemap %s → %d target(s), %d page(s) seeded (of %d relevant)",
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

    def _fetch_target(self, response, source_page: str):
        """Record stats for a fetched target resource and hand it to the profile."""
        self.crawler.stats.inc_value("webscraper/files_downloaded")
        self.crawler.stats.inc_value("webscraper/bytes_downloaded", len(response.body))
        logger.info(
            "[%s] Fetched %s (%d bytes) from %s",
            self.job_id, response.url, len(response.body), source_page,
        )
        yield from self.profile.extract_target(response, source_page, self)

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
