"""
Scrapy settings for the webscraper project.

All tuneable values are read from environment variables so the same
codebase runs locally, in Docker, and on AWS Lambda without any code
changes — only the environment differs.
"""

import os

from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------

BOT_NAME = "webscraper"
SPIDER_MODULES = ["webscraper.spiders"]
NEWSPIDER_MODULE = "webscraper.spiders"

USER_AGENT = os.getenv(
    "USER_AGENT",
    "webscraper/1.0 (+https://github.com/yourorg/webscraper)",
)

# ---------------------------------------------------------------------------
# Ethical scraping
# ---------------------------------------------------------------------------

ROBOTSTXT_OBEY = True

DOWNLOAD_DELAY = float(os.getenv("DOWNLOAD_DELAY", "1"))
RANDOMIZE_DOWNLOAD_DELAY = True

CONCURRENT_REQUESTS = int(os.getenv("CONCURRENT_REQUESTS", "4"))
CONCURRENT_REQUESTS_PER_DOMAIN = 2

AUTOTHROTTLE_ENABLED = True
AUTOTHROTTLE_START_DELAY = DOWNLOAD_DELAY
AUTOTHROTTLE_MAX_DELAY = 10.0
AUTOTHROTTLE_TARGET_CONCURRENCY = 1.0

# ---------------------------------------------------------------------------
# HTTP cache (speeds up re-runs during development; disable in production)
# ---------------------------------------------------------------------------

HTTPCACHE_ENABLED = os.getenv("HTTPCACHE_ENABLED", "false").lower() == "true"
HTTPCACHE_EXPIRATION_SECS = 3600
HTTPCACHE_DIR = "httpcache"

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FORMAT = "%(asctime)s [%(name)s] %(levelname)s: %(message)s"

# Disable Scrapy's own file logging — our utils/logging_config.py handles it
LOG_FILE = None
LOG_ENABLED = True

# ---------------------------------------------------------------------------
# Storage feature flags
# ---------------------------------------------------------------------------

LOCAL_ENABLED = os.getenv("LOCAL_ENABLED", "true").lower() == "true"
S3_ENABLED = os.getenv("S3_ENABLED", "false").lower() == "true"
S3_BUCKET = os.getenv("S3_BUCKET", "")

# ---------------------------------------------------------------------------
# Job orchestration
# ---------------------------------------------------------------------------

# Max number of URL jobs to crawl concurrently in a single batch run.
MAX_CONCURRENT_JOBS = int(os.getenv("MAX_CONCURRENT_JOBS", "10"))

# Persistent registry of already-scraped URLs (loop / re-scrape guard).
VISITED_STORE_PATH = os.getenv("VISITED_STORE_PATH", "state/visited.json")

# ---------------------------------------------------------------------------
# Item pipelines
#
# Priority order: lower number = runs first.
# Add new pipelines here — no other file needs changing.
#
# Example future pipelines:
#   "webscraper.pipelines.database_pipeline.DatabasePipeline": 400
#   "webscraper.pipelines.ai_pipeline.AIPipeline": 500
# ---------------------------------------------------------------------------

ITEM_PIPELINES = {}

if LOCAL_ENABLED:
    ITEM_PIPELINES[
        "webscraper.pipelines.local_storage_pipeline.LocalStoragePipeline"
    ] = 200

if S3_ENABLED:
    ITEM_PIPELINES[
        "webscraper.pipelines.s3_pipeline.S3Pipeline"
    ] = 300

# ---------------------------------------------------------------------------
# Downloader middlewares
# ---------------------------------------------------------------------------

DOWNLOADER_MIDDLEWARES = {
    "scrapy.downloadermiddlewares.robotstxt.RobotsTxtMiddleware": 100,
    "webscraper.middlewares.polite_middleware.PoliteMiddleware": 200,
    "scrapy.downloadermiddlewares.httpcompression.HttpCompressionMiddleware": 810,
}

# ---------------------------------------------------------------------------
# Request fingerprinting (Scrapy 2.7+)
# ---------------------------------------------------------------------------

REQUEST_FINGERPRINTER_IMPLEMENTATION = "2.7"
TWISTED_REACTOR = "twisted.internet.asyncioreactor.AsyncioSelectorReactor"

# ---------------------------------------------------------------------------
# Misc
# ---------------------------------------------------------------------------

FEED_EXPORT_ENCODING = "utf-8"
TELNETCONSOLE_ENABLED = False
