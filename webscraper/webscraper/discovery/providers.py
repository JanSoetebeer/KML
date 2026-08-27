"""
Search-engine backends for external URL discovery.

Discovery *seeds* the crawl with document URLs found by a search engine, instead
of relying only on the crawler pathing to them from the seed page. This is the
fix for the two biggest recall gaps observed in the 411-uni run:

* **0-document universities** — the handbooks exist at guessable URLs
  (``…/uploads/tx_studiengang/modulebook_*.pdf``,
  ``…/fileadmin/…/modulhandbuch_*.pdf``) that the crawl never reached because the
  path was behind JS, a search box, or simply too deep for the page budget.
* **Low per-university recall** — a search query surfaces handbooks the
  best-first crawl would only reach after exhausting its budget on other pages.

Why this lives *outside* Scrapy
-------------------------------
Search endpoints are queried directly (stdlib ``urllib``), not through the
crawler: the crawler runs with ``ROBOTSTXT_OBEY=True`` and would refuse to fetch
a search engine's results path. Discovery is a batch pre-step that produces a
``{domain: [urls]}`` map; those URLs are then handed to the crawl as extra seeds.

Providers (select via ``SEARCH_PROVIDER``)
------------------------------------------
* ``commoncrawl`` — free, no key. Queries the Common Crawl CDX index (a public
  dataset hosted in AWS S3). Bulk-friendly and un-throttled, but the index lags a
  few months and does not capture every PDF.
* ``duckduckgo`` — free, no key. Scrapes the DuckDuckGo HTML endpoint. Fresh
  results, but rate-limited — space queries out (a few seconds each).
* ``google`` — Google Custom Search JSON API. Needs ``GOOGLE_API_KEY`` +
  ``GOOGLE_CSE_ID``. Highest quality; 100 queries/day free, then $5/1,000.

Every provider returns a de-duplicated list of same-domain document URLs.
Pure stdlib — no third-party HTTP client — so it runs anywhere the scraper runs.
"""

from __future__ import annotations

import json
import logging
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from html import unescape

logger = logging.getLogger(__name__)

# A browser-ish UA: the default urllib agent is blocked by several endpoints
# (DuckDuckGo in particular). This is a plain public search query, not scraping
# behind auth.
_UA = (
    "Mozilla/5.0 (compatible; webscraper-discovery/1.0; "
    "+https://github.com/yourorg/webscraper)"
)

# Document extensions worth seeding. Kept in sync with the modulhandbuch profile.
_DOC_EXTS = (".pdf", ".doc", ".docx")

# Broad URL stems for *client-side* filtering (Common Crawl returns every doc
# capture on a domain; we keep the handbook-like ones). Deliberately short so
# real-world spellings all match — ``modul`` covers modulhandbuch / modulbook /
# modulebook / modulbeschreibung; ``handbuch`` covers standalone handbuch files.
# Over-seeding is cheap: the classifier is the precision gate, discovery only
# needs recall. Used by CommonCrawlProvider (search-API providers query by
# phrase instead, so they don't need these).
_URL_STEMS = (
    "modul", "mhb", "handbuch", "curric", "studienplan", "studienverlauf",
    "pruefungsordnung", "spo", "stupo",
)


def _base_domain(host: str) -> str:
    """Last two DNS labels, e.g. ``www.uni-x.de`` → ``uni-x.de``."""
    labels = (host or "").lower().strip(".").split(".")
    return ".".join(labels[-2:]) if len(labels) >= 2 else (host or "").lower()


def _is_doc_url(url: str) -> bool:
    path = urllib.parse.urlparse(url).path.lower()
    return path.endswith(_DOC_EXTS)


def _http_get(url: str, timeout: float = 20.0, data: bytes | None = None,
              retries: int = 3, backoff: float = 1.5) -> str:
    """GET/POST returning decoded text.

    Retries transient failures — connection drops/timeouts and HTTP 429/5xx —
    with exponential backoff. The Common Crawl index server in particular throttles
    bursts by closing the connection ("Remote end closed connection without
    response"), which is guaranteed to happen somewhere in a 400-domain batch.
    A 4xx (other than 429) is a semantic answer (e.g. 404 = no captures) and is
    re-raised immediately without retrying.
    """
    req = urllib.request.Request(url, data=data, headers={"User-Agent": _UA})
    last: Exception | None = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                charset = resp.headers.get_content_charset() or "utf-8"
                return resp.read().decode(charset, "replace")
        except urllib.error.HTTPError as exc:
            if exc.code != 429 and exc.code < 500:
                raise  # client error — retrying won't help
            last = exc
        except Exception as exc:  # noqa: BLE001 — URLError, timeout, conn reset
            last = exc
        if attempt < retries - 1:
            time.sleep(backoff * (2 ** attempt))
    raise last if last else RuntimeError("request failed")


class SearchProvider:
    """Base class: turn (domain, terms) into a list of same-domain doc URLs."""

    name = "base"

    def __init__(self, *, per_query_delay: float = 0.0, max_results: int = 20):
        self.per_query_delay = per_query_delay
        self.max_results = max_results

    def search(self, domain: str, terms: list[str]) -> list[str]:
        """Return de-duplicated document URLs on *domain* matching any *term*."""
        raise NotImplementedError

    # -- shared helpers --------------------------------------------------------

    def _keep(self, domain: str, urls: list[str]) -> list[str]:
        """Filter to same-base-domain document URLs, de-duplicated, order-stable."""
        base = _base_domain(domain)
        seen: set[str] = set()
        out: list[str] = []
        for u in urls:
            if not u or u in seen:
                continue
            host = urllib.parse.urlparse(u).hostname or ""
            if _base_domain(host) != base or not _is_doc_url(u):
                continue
            seen.add(u)
            out.append(u)
        return out


class CommonCrawlProvider(SearchProvider):
    """Query the Common Crawl CDX index for captured document URLs on a domain.

    Queries the newest ``indexes`` monthly snapshots and unions the results: a
    handbook captured in an earlier crawl but missing from the latest one is
    still found, which measurably lifts recall for free (each snapshot is a
    partial view of the web).
    """

    name = "commoncrawl"
    _COLLINFO = "https://index.commoncrawl.org/collinfo.json"

    def __init__(self, index_url: str | None = None, indexes: int = 3, **kw):
        super().__init__(**kw)
        # Resolve the newest N monthly indexes once (e.g. CC-MAIN-2026-30, -26 …),
        # cached on the instance so a batch of domains resolves them a single time.
        if index_url:
            self._index_urls = [index_url]
        else:
            self._index_urls = self._latest_index_urls(max(1, indexes))

    def _latest_index_urls(self, n: int) -> list[str]:
        try:
            info = json.loads(_http_get(self._COLLINFO))
            # collinfo.json is newest-first; each entry has a "cdx-api" endpoint.
            return [entry["cdx-api"] for entry in info[:n]]
        except Exception as exc:  # noqa: BLE001 — degrade to no-op if unreachable
            logger.warning("CommonCrawl: could not resolve indexes (%s)", exc)
            return []

    def _query_index(self, index_url: str, base: str) -> list[str]:
        """Captured document URLs for *base* in a single monthly index."""
        # CDX query form validated against the live index: match the whole
        # registered domain (all subdomains — handbooks often live on faculty /
        # module-DB subdomains like ``moduldb.htwsaar.de``), and filter to
        # document captures. The ``~`` prefix marks the value as a regex (plain
        # ``url:`` 404s here). A 404 means "no captures for this domain".
        query = urllib.parse.urlencode({
            "url": base,
            "matchType": "domain",
            "output": "json",
            "fl": "url",
            "filter": r"~url:.*\.(pdf|doc|docx|PDF|DOC|DOCX)",
            "limit": "50000",
        })
        try:
            body = _http_get(f"{index_url}?{query}", timeout=45.0)
        except urllib.error.HTTPError as exc:
            if exc.code == 404:  # no captures for this domain in this index
                return []
            logger.warning("CommonCrawl HTTP %s for %s", exc.code, base)
            return []
        except Exception as exc:  # noqa: BLE001 — one bad index must not abort the rest
            logger.warning("CommonCrawl query failed for %s (%s)", base, exc)
            return []
        finally:
            if self.per_query_delay:
                time.sleep(self.per_query_delay)
        out: list[str] = []
        for line in body.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line).get("url", ""))
            except json.JSONDecodeError:
                continue
        return out

    def search(self, domain: str, terms: list[str]) -> list[str]:
        if not self._index_urls:
            return []
        base = _base_domain(domain)
        # Match on broad URL stems (union with any caller-supplied terms) — the
        # capture list is URL-only, so phrase queries don't apply here.
        stems = list(_URL_STEMS) + [_fold(t) for t in terms]
        seen: set[str] = set()
        matched: list[str] = []
        for index_url in self._index_urls:
            for url in self._query_index(index_url, base):
                if url and url not in seen and _matches_terms(url, stems):
                    seen.add(url)
                    matched.append(url)
        return self._keep(base, matched)[: self.max_results]


class DuckDuckGoProvider(SearchProvider):
    """Scrape the DuckDuckGo HTML endpoint. Free, fresh, but rate-limited."""

    name = "duckduckgo"
    _ENDPOINT = "https://html.duckduckgo.com/html/"
    # DuckDuckGo wraps outbound links as /l/?uddg=<url-encoded target>.
    _RESULT_RE = re.compile(r'<a[^>]+class="result__a"[^>]+href="([^"]+)"')
    _UDDG_RE = re.compile(r"[?&]uddg=([^&]+)")

    def __init__(self, *, per_query_delay: float = 3.0, **kw):
        # Default to a polite gap between queries — DDG blocks rapid bursts.
        super().__init__(per_query_delay=per_query_delay, **kw)

    def search(self, domain: str, terms: list[str]) -> list[str]:
        base = _base_domain(domain)
        found: list[str] = []
        for term in terms:
            q = f"site:{base} {term} filetype:pdf"
            data = urllib.parse.urlencode({"q": q}).encode()
            try:
                html = _http_get(self._ENDPOINT, data=data, timeout=20.0)
            except Exception as exc:  # noqa: BLE001 — one bad term must not abort
                logger.warning("DuckDuckGo query failed (%s): %s", q, exc)
                html = ""
            finally:
                if self.per_query_delay:
                    time.sleep(self.per_query_delay)
            for raw in self._RESULT_RE.findall(html):
                found.append(self._unwrap(raw))
            if len(self._keep(base, found)) >= self.max_results:
                break
        return self._keep(base, found)[: self.max_results]

    def _unwrap(self, href: str) -> str:
        href = unescape(href)
        if href.startswith("//"):
            href = "https:" + href
        m = self._UDDG_RE.search(href)
        return urllib.parse.unquote(m.group(1)) if m else href


class GoogleCSEProvider(SearchProvider):
    """Google Custom Search JSON API. Needs an API key + Search-Engine ID (cx)."""

    name = "google"
    _ENDPOINT = "https://www.googleapis.com/customsearch/v1"

    def __init__(self, api_key: str, cse_id: str, **kw):
        super().__init__(**kw)
        self.api_key = api_key
        self.cse_id = cse_id

    def search(self, domain: str, terms: list[str]) -> list[str]:
        if not (self.api_key and self.cse_id):
            logger.warning("GoogleCSE: missing GOOGLE_API_KEY / GOOGLE_CSE_ID")
            return []
        base = _base_domain(domain)
        found: list[str] = []
        for term in terms:
            q = f"site:{base} {term} filetype:pdf"
            params = urllib.parse.urlencode({
                "key": self.api_key, "cx": self.cse_id, "q": q, "num": 10,
            })
            try:
                data = json.loads(_http_get(f"{self._ENDPOINT}?{params}"))
            except urllib.error.HTTPError as exc:
                # 429 = daily free quota spent; stop querying to avoid charges.
                logger.warning("GoogleCSE HTTP %s for %s (%s)", exc.code, base, q)
                if exc.code in (403, 429):
                    break
                data = {}
            except Exception as exc:  # noqa: BLE001
                logger.warning("GoogleCSE query failed (%s): %s", q, exc)
                data = {}
            finally:
                if self.per_query_delay:
                    time.sleep(self.per_query_delay)
            for item in data.get("items", []):
                if item.get("link"):
                    found.append(item["link"])
            if len(self._keep(base, found)) >= self.max_results:
                break
        return self._keep(base, found)[: self.max_results]


# --------------------------------------------------------------------------- #
# Shared term matching (umlaut-folded, like the crawl profile's keyword scoring)
# --------------------------------------------------------------------------- #

_FOLD = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"})


def _fold(text: str) -> str:
    return (text or "").lower().translate(_FOLD)


def _matches_terms(url: str, folded_terms: list[str]) -> bool:
    """True if any search term appears in the folded URL (client-side filter)."""
    hay = _fold(url)
    return any(t in hay for t in folded_terms) if folded_terms else True


def get_provider(name: str, *, api_key: str = "", cse_id: str = "",
                 per_query_delay: float = 0.0, max_results: int = 20,
                 indexes: int = 3) -> SearchProvider:
    """Factory: build a provider by name. Unknown names raise ``ValueError``."""
    name = (name or "").lower().strip()
    if name == "commoncrawl":
        return CommonCrawlProvider(indexes=indexes, per_query_delay=per_query_delay,
                                   max_results=max_results)
    if name == "duckduckgo":
        return DuckDuckGoProvider(max_results=max_results)
    if name == "google":
        return GoogleCSEProvider(api_key=api_key, cse_id=cse_id,
                                 per_query_delay=per_query_delay, max_results=max_results)
    raise ValueError(f"unknown SEARCH_PROVIDER {name!r} "
                     "(expected: commoncrawl | duckduckgo | google)")
