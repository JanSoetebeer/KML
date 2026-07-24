"""
Extraction profiles — the pluggable, use-case-specific layer of the crawler.

The crawl *engine* (:class:`~webscraper.spiders.document_spider.DocumentSpider`)
is generic: it fetches pages, schedules the frontier best-first, seeds from
sitemaps, discovers faculty subdomains and enforces the depth/page budget — none
of which is specific to *what* is being extracted. Everything use-case-specific
lives in an :class:`~webscraper.profiles.base.ExtractionProfile`, selected by name
via ``CRAWL_PROFILE`` / ``--profile``.

Add a new extraction need by dropping a profile module in this package and
registering it in :mod:`webscraper.profiles.registry` — no engine changes.
"""

from webscraper.profiles.base import ExtractionProfile
from webscraper.profiles.registry import (
    available_profiles,
    get_profile,
)

__all__ = ["ExtractionProfile", "get_profile", "available_profiles"]
