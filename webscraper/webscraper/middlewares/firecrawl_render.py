"""
JS-rendering downloader middleware (Firecrawl).

Some university sites are JavaScript apps: a plain fetch returns an empty shell,
so the crawler sees no links and no handbooks (the "0 documents" universities).
This middleware routes *page* requests through Firecrawl's ``/scrape`` endpoint,
which runs a real browser and returns the **rendered** HTML — so link-following,
sitemap hubs, and PDF-link discovery all work on JS sites, using the exact same
crawl engine and profiles. Document fetches (PDF/DOCX) are left to Scrapy's normal
downloader, so nothing changes for the bytes that matter.

It is **opt-in and use-case-agnostic**: enable with ``RENDER_JS=true`` (+
``FIRECRAWL_API_KEY``) for a targeted run over JS-heavy domains; off by default,
the crawl is byte-for-byte unchanged. Any profile benefits — this is an engine
capability, not a Modulhandbuch-specific one.

Cost & concurrency note: each rendered page is one Firecrawl credit, and the
scrape call blocks briefly. Use it for a focused pass over the domains that
returned 0, at low concurrency — not for a full 400-university crawl.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from urllib.parse import urlparse

from scrapy.exceptions import NotConfigured
from scrapy.http import HtmlResponse

from webscraper.spiders.document_spider import _NON_PAGE_EXTENSIONS

logger = logging.getLogger(__name__)


class FirecrawlRenderMiddleware:
    """Render page requests via Firecrawl so the crawler sees JS-built content."""

    _ENDPOINT = "https://api.firecrawl.dev/v1/scrape"

    def __init__(self, api_key: str, timeout: float):
        if not api_key:
            raise NotConfigured(
                "RENDER_JS=true but FIRECRAWL_API_KEY is not set — cannot render."
            )
        self._api_key = api_key
        self._timeout = timeout
        logger.info("FirecrawlRenderMiddleware active — JS page rendering ON")

    @classmethod
    def from_crawler(cls, crawler):
        s = crawler.settings
        if not s.getbool("RENDER_JS", False):
            raise NotConfigured  # disabled → not installed, zero overhead
        return cls(
            api_key=s.get("FIRECRAWL_API_KEY", ""),
            timeout=s.getfloat("RENDER_TIMEOUT", 60.0),
        )

    def _should_render(self, request) -> bool:
        """Render HTML *pages* only; let documents/assets download normally."""
        if request.meta.get("firecrawl_rendered"):
            return False  # already rendered — never loop
        if request.method != "GET":
            return False
        path = urlparse(request.url).path.lower()
        last = path.rsplit("/", 1)[-1]
        ext = "." + last.rsplit(".", 1)[-1] if "." in last else ""
        return ext not in _NON_PAGE_EXTENSIONS

    def _scrape(self, url: str) -> str | None:
        """Fetch rendered HTML for *url* via Firecrawl, or None on any failure."""
        payload = json.dumps({
            "url": url,
            "formats": ["html"],
            "onlyMainContent": False,
        }).encode()
        req = urllib.request.Request(
            self._ENDPOINT, data=payload,
            headers={"Authorization": f"Bearer {self._api_key}",
                     "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                data = json.loads(resp.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as exc:
            logger.warning("Firecrawl render HTTP %s for %s", exc.code, url)
            return None
        except Exception as exc:  # noqa: BLE001 — fall back to normal download
            logger.warning("Firecrawl render failed for %s (%s)", url, exc)
            return None
        # /scrape shape: {"success": true, "data": {"html": "...", ...}}
        return (data.get("data") or {}).get("html")

    def process_request(self, request, spider):
        if not self._should_render(request):
            return None  # normal Scrapy download (documents, assets, retries)
        html = self._scrape(request.url)
        if not html:
            return None  # graceful fallback — let Scrapy fetch the raw shell
        # Hand the rendered HTML back as the response for this request; mark it so
        # a re-schedule of the same URL isn't rendered twice.
        request.meta["firecrawl_rendered"] = True
        return HtmlResponse(
            url=request.url, body=html.encode("utf-8"),
            encoding="utf-8", request=request,
        )
