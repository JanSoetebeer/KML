import abc
import logging
import uuid
from datetime import datetime, timezone

import scrapy

logger = logging.getLogger(__name__)


class BaseSpider(scrapy.Spider, abc.ABC):
    """
    Abstract base for all webscraper spiders.

    Subclasses must implement :meth:`parse` and should call
    ``super().__init__()`` to receive the shared job_id and crawled_at
    timestamp.

    Extension guide
    ---------------
    To add a new spider type (e.g. ``ArticleSpider``, ``AIKeywordSpider``):

    1. Create ``webscraper/spiders/my_spider.py``.
    2. Subclass ``BaseSpider``.
    3. Override ``parse()`` and, optionally, ``start_requests()``.
    4. Add any spider-specific settings to ``custom_settings``.
    5. Register no wiring elsewhere — Scrapy auto-discovers spiders.
    """

    # Subclasses must set a unique name, e.g. name = "document"
    name: str = NotImplemented

    def __init__(self, *args, job_id: str | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.job_id: str = job_id or uuid.uuid4().hex
        self.crawled_at: str = datetime.now(timezone.utc).isoformat()
        logger.info(
            "[%s] Spider '%s' initialised — crawled_at=%s",
            self.job_id,
            self.name,
            self.crawled_at,
        )

    @abc.abstractmethod
    def parse(self, response, **kwargs):
        """Entry point for response parsing. Must be implemented by subclasses."""

    def closed(self, reason: str) -> None:
        logger.info(
            "[%s] Spider '%s' closed — reason=%s",
            self.job_id,
            self.name,
            reason,
        )
