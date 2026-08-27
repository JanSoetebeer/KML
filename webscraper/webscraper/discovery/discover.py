"""
Discovery orchestration: run a search provider over a list of domains and
collect the document URLs it finds.

The output is a ``{domain: [urls]}`` map (also serialisable to JSONL) that the
crawl consumes as extra high-priority seeds — see ``DocumentSpider`` /
``bulk_run``. Kept separate from the providers so the batch policy (per-domain
error isolation, progress logging, de-dup) lives in one place.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from urllib.parse import urlparse

from webscraper.discovery.providers import SearchProvider, _base_domain

logger = logging.getLogger(__name__)

# Default search terms if the caller passes none. Mirrors the strongest
# Modulhandbuch-profile tokens; ``filetype:pdf`` is added per-provider.
DEFAULT_TERMS = ("modulhandbuch", "modulbeschreibung", "modulhandbücher",
                 "module handbook", "modulebook")


def domains_from_urls(urls: list[str]) -> list[str]:
    """Collapse seed URLs to their unique registered domains, order-stable."""
    seen: set[str] = set()
    out: list[str] = []
    for u in urls:
        host = urlparse(u if "//" in u else f"https://{u}").hostname or ""
        base = _base_domain(host)
        if base and base not in seen:
            seen.add(base)
            out.append(base)
    return out


def discover_for_domains(
    domains: list[str],
    provider: SearchProvider,
    terms: list[str] | None = None,
    progress: bool = True,
) -> dict[str, list[str]]:
    """
    Query *provider* for each domain and return ``{domain: [doc_urls]}``.

    A failure on one domain is logged and skipped — a batch of 400 domains never
    aborts because one search errored.
    """
    terms = list(terms) if terms else list(DEFAULT_TERMS)
    results: dict[str, list[str]] = {}
    total = len(domains)
    for i, domain in enumerate(domains, 1):
        base = _base_domain(domain)
        try:
            urls = provider.search(base, terms)
        except Exception as exc:  # noqa: BLE001 — isolate per-domain failures
            logger.warning("discovery failed for %s (%s)", base, exc)
            urls = []
        results[base] = urls
        if progress:
            logger.info("[discovery %d/%d] %s → %d url(s) via %s",
                        i, total, base, len(urls), provider.name)
    return results


def load_discovery_seeds(path: str) -> dict[str, list[str]]:
    """
    Load a discovered-URL JSONL (``{"domain": ..., "url": ...}`` per line) into a
    ``{base_domain: [urls]}`` map for the crawl to seed from. Missing file → ``{}``
    (discovery is optional; the crawl runs normally without it).
    """
    p = Path(path)
    if not p.exists():
        logger.warning("discovery seeds file not found: %s", path)
        return {}
    seeds: dict[str, list[str]] = {}
    with p.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            domain, url = _base_domain(rec.get("domain", "")), rec.get("url", "")
            if domain and url:
                seeds.setdefault(domain, []).append(url)
    return seeds


def summarize(results: dict[str, list[str]]) -> dict:
    """Batch stats: how many domains got hits, total URLs, coverage rate."""
    with_hits = sum(1 for v in results.values() if v)
    total_urls = sum(len(v) for v in results.values())
    n = len(results)
    return {
        "domains": n,
        "domains_with_hits": with_hits,
        "coverage_rate": round(with_hits / n, 4) if n else 0.0,
        "total_urls": total_urls,
        "urls_per_domain_mean": round(total_urls / n, 2) if n else 0.0,
    }
