import logging

from scrapy import signals
from scrapy.exceptions import NotConfigured

logger = logging.getLogger(__name__)


class PoliteMiddleware:
    """
    Downloader middleware that enforces ethical crawling practices.

    Features
    --------
    - Respects ``robots.txt`` (delegated to Scrapy's built-in handler via
      ``ROBOTSTXT_OBEY = True`` in settings — this middleware logs a reminder).
    - Attaches a custom ``User-Agent`` header to every request so servers can
      identify the bot and contact the operator.
    - Logs a warning when ``DOWNLOAD_DELAY`` is set below the recommended
      minimum.

    Configuration (settings.py / env)
    ----------------------------------
    ``USER_AGENT``
        Sent with every request.
    ``DOWNLOAD_DELAY``
        Minimum seconds between requests to the same domain.
    ``ROBOTSTXT_OBEY``
        Must be ``True`` (enforced by this middleware at startup).

    To disable this middleware, remove it from ``DOWNLOADER_MIDDLEWARES``
    in ``settings.py``.
    """

    _MIN_RECOMMENDED_DELAY = 0.5

    def __init__(self, user_agent: str, download_delay: float, obey_robots: bool):
        self._user_agent = user_agent
        if not obey_robots:
            raise NotConfigured(
                "ROBOTSTXT_OBEY must be True for ethical scraping. "
                "Set ROBOTSTXT_OBEY=True in settings.py."
            )
        if download_delay < self._MIN_RECOMMENDED_DELAY:
            logger.warning(
                "DOWNLOAD_DELAY=%.1f is below the recommended minimum of %.1f s. "
                "Consider increasing it to avoid overloading servers.",
                download_delay,
                self._MIN_RECOMMENDED_DELAY,
            )
        logger.info(
            "PoliteMiddleware active — user_agent=%r  delay=%.1fs  robots=True",
            self._user_agent,
            download_delay,
        )

    @classmethod
    def from_crawler(cls, crawler):
        return cls(
            user_agent=crawler.settings.get("USER_AGENT", "webscraper/1.0"),
            download_delay=crawler.settings.getfloat("DOWNLOAD_DELAY", 1.0),
            obey_robots=crawler.settings.getbool("ROBOTSTXT_OBEY", True),
        )

    def process_request(self, request, spider):
        request.headers.setdefault("User-Agent", self._user_agent)
        return None

    def process_response(self, request, response, spider):
        return response

    def process_exception(self, request, exception, spider):
        logger.warning(
            "[%s] Exception on %s: %s",
            getattr(spider, "job_id", "?"),
            request.url,
            repr(exception),
        )
        return None
