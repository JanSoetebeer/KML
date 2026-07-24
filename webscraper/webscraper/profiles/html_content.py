"""
HTML-content profile — EXAMPLE / TEMPLATE.

Demonstrates the second and third extraction shapes (HTML content extraction and
structured-field extraction) on the same crawl engine. It downloads **no files**
(``target_extensions`` is empty); instead every crawled HTML page is turned into
a :class:`~webscraper.items.ContentItem`.

This is intentionally generic — a starting point to copy per concrete need
(news articles, course catalogues, event listings, staff directories, …). To
specialise it:

* set :attr:`POSITIVE_TOKENS` / :attr:`NEGATIVE_TOKENS` (or override
  ``score_link``) to steer the crawl toward the relevant section;
* replace the body/title selectors in ``extract_page`` with the ones that match
  your target pages; and
* populate the ``fields`` dict for structured extraction (e.g.
  ``fields={"date": ..., "location": ...}``) instead of, or alongside, ``text``.

A dedicated pipeline can then persist :class:`ContentItem` (the existing
document pipelines ignore it, so nothing breaks by shipping this profile).
"""

from datetime import datetime, timezone

from scrapy.http import TextResponse

from webscraper.items import ContentItem
from webscraper.profiles.base import ExtractionProfile


class HTMLContentProfile(ExtractionProfile):
    name = "html-content"
    target_extensions = frozenset()  # extract from pages, download nothing

    def extract_page(self, response, spider):
        if not isinstance(response, TextResponse):
            return
        title = (response.css("title::text").get() or "").strip()
        # Naive main-text extraction — replace with selectors tuned to the pages
        # you care about (or a readability pass) for a real content need.
        paragraphs = [t.strip() for t in response.css("p::text").getall() if t.strip()]
        text = "\n".join(paragraphs)
        if not (title or text):
            return
        yield ContentItem(
            url=response.url,
            title=title,
            text=text,
            fields={},  # structured-field slot — fill per concrete use case
            crawled_at=datetime.now(timezone.utc).isoformat(),
            job_id=spider.job_id,
            extra={},
        )
