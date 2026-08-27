"""External URL discovery (search-engine seeding) for the crawl.

Public API::

    from webscraper.discovery import get_provider, discover_for_domains

See :mod:`webscraper.discovery.providers` for the backends and
:mod:`webscraper.discovery.discover` for the batch orchestration.
"""

from webscraper.discovery.discover import (
    DEFAULT_TERMS,
    discover_for_domains,
    domains_from_urls,
    load_discovery_seeds,
    summarize,
)
from webscraper.discovery.providers import SearchProvider, get_provider

__all__ = [
    "get_provider",
    "SearchProvider",
    "discover_for_domains",
    "domains_from_urls",
    "load_discovery_seeds",
    "summarize",
    "DEFAULT_TERMS",
]
