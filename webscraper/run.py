"""
CLI entrypoint for the webscraper.

Usage
-----
    python run.py <url> [--job-id <id>] [--log-level DEBUG|INFO|WARNING]

Examples
--------
    python run.py https://example.com/resources
    python run.py https://example.com/docs --log-level DEBUG
    python run.py https://example.com --job-id my-run-001
"""

import argparse
import logging
import os
import sys
import uuid

from dotenv import load_dotenv

load_dotenv()

os.environ.setdefault("SCRAPY_SETTINGS_MODULE", "webscraper.settings")

from scrapy.crawler import CrawlerProcess
from scrapy.utils.project import get_project_settings

from webscraper.utils.logging_config import configure as configure_logging
from webscraper.validators.url_validator import URLValidationError, validate


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Webscraper — download documents from a given URL."
    )
    parser.add_argument("url", help="Seed URL to scrape (http/https).")
    parser.add_argument(
        "--job-id",
        default=None,
        help="Unique run identifier (default: auto-generated UUID).",
    )
    parser.add_argument(
        "--log-level",
        default=os.getenv("LOG_LEVEL", "INFO"),
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging verbosity (default: INFO).",
    )
    parser.add_argument(
        "--no-ping",
        action="store_true",
        help="Skip the HEAD-request reachability check during URL validation.",
    )
    return parser.parse_args(argv)


def run(url: str, job_id: str, log_level: str = "INFO", ping: bool = True) -> int:
    """
    Validate *url* and start the document spider.

    Returns
    -------
    int
        Exit code: 0 on success, 1 on validation failure, 2 on crawl error.
    """
    configure_logging(job_id=job_id, level=log_level)
    logger = logging.getLogger(__name__)

    logger.info("=== webscraper job started  job_id=%s ===", job_id)

    # --- URL validation -------------------------------------------------------
    try:
        validated_url = validate(url, ping=ping)
    except URLValidationError as exc:
        logger.error("URL validation failed: %s", exc)
        return 1

    # --- Spider ---------------------------------------------------------------
    from webscraper.spiders.document_spider import DocumentSpider

    settings = get_project_settings()
    settings.set("LOG_LEVEL", log_level)

    process = CrawlerProcess(settings)
    process.crawl(DocumentSpider, start_url=validated_url, job_id=job_id)

    try:
        process.start()
    except Exception as exc:
        logger.error("Crawl process raised an unexpected error: %s", exc)
        return 2

    logger.info("=== webscraper job finished  job_id=%s ===", job_id)
    return 0


def main(argv=None) -> None:
    args = parse_args(argv)
    job_id = args.job_id or uuid.uuid4().hex
    exit_code = run(
        url=args.url,
        job_id=job_id,
        log_level=args.log_level,
        ping=not args.no_ping,
    )
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
