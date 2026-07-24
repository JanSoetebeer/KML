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
# Download safety limits
#
# Without these, media-heavy pages (many images, or large/streaming videos)
# can stall a run until the Lambda subprocess is killed — which looks like a
# hang/"endless loop". Each is env-overridable.
# ---------------------------------------------------------------------------

# Abort a single request that takes too long (default Scrapy value is 180s).
DOWNLOAD_TIMEOUT = int(os.getenv("DOWNLOAD_TIMEOUT", "60"))

# Hard cap on a single file's size (bytes). Files larger than this are dropped
# instead of being buffered fully into memory. Default 50 MB.
DOWNLOAD_MAXSIZE = int(os.getenv("DOWNLOAD_MAXSIZE", str(50 * 1024 * 1024)))
DOWNLOAD_WARNSIZE = int(os.getenv("DOWNLOAD_WARNSIZE", str(20 * 1024 * 1024)))

# Don't multiply slow requests with many retries.
RETRY_TIMES = int(os.getenv("RETRY_TIMES", "1"))

# Safety cap: stop the crawl after this many downloaded files per run so a
# link-heavy page can't run indefinitely. 0 disables the cap.
CLOSESPIDER_ITEMCOUNT = int(os.getenv("MAX_ITEMS_PER_RUN", "200"))

# Bounded deep crawl (DocumentSpider follows same-site links to find documents
# that aren't linked from the seed page). Keep these small to stay polite and
# bounded — a university site can be enormous. The crawl is best-first: within
# this budget the highest-scoring (most Modulhandbuch-like) pages are visited
# first, so raising the budget is rarely necessary to improve recall.
CRAWL_MAX_DEPTH = int(os.getenv("CRAWL_MAX_DEPTH", "2"))
CRAWL_MAX_PAGES = int(os.getenv("CRAWL_MAX_PAGES", "60"))

# Sitemap discovery: fetch /sitemap.xml (and robots.txt-declared sitemaps) to
# find document/hub URLs directly, skipping the depth traversal for them.
CRAWL_USE_SITEMAP = os.getenv("CRAWL_USE_SITEMAP", "true").lower() == "true"
# Cap on how many relevant hub pages to seed from a sitemap's <urlset>.
CRAWL_MAX_SITEMAP_URLS = int(os.getenv("CRAWL_MAX_SITEMAP_URLS", "50"))
# Cap on child sitemaps followed from a sitemap index (highest-scoring first).
CRAWL_MAX_CHILD_SITEMAPS = int(os.getenv("CRAWL_MAX_CHILD_SITEMAPS", "10"))

# Backstop: also stop a crawl after this many fetched pages (Scrapy built-in).
CLOSESPIDER_PAGECOUNT = int(os.getenv("CLOSESPIDER_PAGECOUNT", "400"))

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
# ML classification (Modulhandbuch classifier)
#
# When enabled, each downloaded document is scored by the trained model and the
# verdict is written to a per-crawl review manifest (output/_review/). Disabled
# by default and degrades to a no-op if the model or ML deps aren't present.
# ---------------------------------------------------------------------------

CLASSIFIER_ENABLED = os.getenv("CLASSIFIER_ENABLED", "false").lower() == "true"
# Path to the trained joblib artifact. Empty → mlclassifier's default location.
MODEL_PATH = os.getenv("MODEL_PATH", "")
# Where per-run classification review manifests are written. Must be writable —
# on Lambda only /tmp is (set REVIEW_MANIFEST_DIR=/tmp/review there).
REVIEW_MANIFEST_DIR = os.getenv("REVIEW_MANIFEST_DIR", "")

# ---------------------------------------------------------------------------
# Job orchestration
# ---------------------------------------------------------------------------

# Max number of URL jobs to crawl concurrently in a single batch run.
MAX_CONCURRENT_JOBS = int(os.getenv("MAX_CONCURRENT_JOBS", "10"))

# Persistent registry of already-scraped URLs (loop / re-scrape guard).
# Backend: "json" (local file, default) or "dynamodb" (shared, for Lambda/cloud).
VISITED_STORE_BACKEND = os.getenv("VISITED_STORE_BACKEND", "json")
VISITED_STORE_PATH = os.getenv("VISITED_STORE_PATH", "state/visited.json")
DYNAMODB_TABLE = os.getenv("DYNAMODB_TABLE", "webscraper-visited")

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

if CLASSIFIER_ENABLED:
    # After local storage (200) so the saved file path is known, around S3 (300).
    ITEM_PIPELINES[
        "webscraper.pipelines.classification_pipeline.ClassificationPipeline"
    ] = 250

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
