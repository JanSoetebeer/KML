"""
Concurrency-capped job runner.

Each URL becomes its own *job*: a dedicated :class:`DocumentSpider` crawl with
its own ``job_id``.  Up to ``max_concurrent`` jobs run in parallel (default 10),
mirroring how an AWS Lambda fan-out would process a batch of URLs with a
concurrency limit.

Design
------
- Uses Scrapy's :class:`~scrapy.crawler.CrawlerRunner` (not ``CrawlerProcess``)
  so we control the Twisted reactor and can throttle concurrency with a
  :class:`~twisted.internet.defer.DeferredSemaphore`.
- Consults a :class:`~webscraper.state.visited_store.BaseVisitedStore` before
  launching each job to skip already-scraped sites (``--force`` overrides).
- Marks a URL visited only after its crawl finishes successfully.

Production note
---------------
Locally this runs N concurrent spiders in a single process. In production the
same semantics map to N concurrent Lambda invocations — one job per URL — with
the visited-store backed by DynamoDB / a database instead of a JSON file.
"""

import logging
import time
from dataclasses import dataclass, field

from scrapy.crawler import CrawlerRunner
from twisted.internet import defer

from webscraper.spiders.document_spider import DocumentSpider
from webscraper.state.visited_store import BaseVisitedStore, normalize_url
from webscraper.validators.url_validator import URLValidationError, validate

logger = logging.getLogger(__name__)


@dataclass
class JobResult:
    """Outcome of a single URL job."""

    url: str
    job_id: str
    status: str = "pending"  # scraped | skipped | invalid | error
    detail: str = ""
    files_found: int = 0
    files_downloaded: int = 0
    bytes_downloaded: int = 0


@dataclass
class BatchSummary:
    """Aggregate outcome of a batch of jobs."""

    results: list = field(default_factory=list)
    started_at: float = field(default_factory=time.time)
    finished_at: float | None = None

    def add(self, result: JobResult) -> None:
        self.results.append(result)

    def mark_finished(self) -> None:
        self.finished_at = time.time()

    def counts(self) -> dict:
        out: dict = {}
        for r in self.results:
            out[r.status] = out.get(r.status, 0) + 1
        return out

    def to_dict(self) -> dict:
        """Serialisable summary for the API / results dashboard."""
        end = self.finished_at if self.finished_at is not None else time.time()
        return {
            "counts": self.counts(),
            "total_urls": len(self.results),
            "files_found": sum(r.files_found for r in self.results),
            "files_downloaded": sum(r.files_downloaded for r in self.results),
            "bytes_downloaded": sum(r.bytes_downloaded for r in self.results),
            "duration_seconds": round(max(0.0, end - self.started_at), 2),
            "per_url": [
                {
                    "url": r.url,
                    "status": r.status,
                    "files_found": r.files_found,
                    "files_downloaded": r.files_downloaded,
                    "bytes_downloaded": r.bytes_downloaded,
                    "detail": r.detail,
                }
                for r in self.results
            ],
        }


class JobRunner:
    """Run a batch of URL jobs with a concurrency cap and dedup guard."""

    def __init__(
        self,
        settings,
        visited_store: BaseVisitedStore,
        max_concurrent: int = 10,
        ping: bool = True,
        force: bool = False,
        file_types=None,
        profile=None,
    ):
        self._settings = settings
        self._store = visited_store
        self._max_concurrent = max(1, int(max_concurrent))
        self._ping = ping
        self._force = force
        self._file_types = file_types
        # Active extraction profile name; falls back to the settings default
        # (which itself defaults to "modulhandbuch") when not given.
        self._profile = profile or settings.get("CRAWL_PROFILE")
        self._runner = CrawlerRunner(settings)
        self._summary = BatchSummary()

    def run(self, jobs: list[tuple[str, str]]) -> BatchSummary:
        """
        Execute *jobs* (a list of ``(url, job_id)`` tuples).

        Blocks until all jobs finish, then returns a :class:`BatchSummary`.
        """
        logger.info(
            "Starting batch — %d URL(s), max %d concurrent job(s), force=%s",
            len(jobs),
            self._max_concurrent,
            self._force,
        )

        # Install the configured Twisted reactor BEFORE importing it.
        # CrawlerRunner (unlike CrawlerProcess) does not do this for us, so
        # importing reactor too early would install the default SelectReactor
        # and clash with settings.TWISTED_REACTOR.
        reactor_path = self._settings.get("TWISTED_REACTOR")
        if reactor_path:
            from scrapy.utils.reactor import install_reactor

            install_reactor(reactor_path)
        from twisted.internet import reactor

        sem = defer.DeferredSemaphore(self._max_concurrent)

        def _stop(_result=None):
            """Always stop the reactor exactly once, however we got here."""
            if reactor.running:
                reactor.stop()

        def _start():
            """Dispatch all jobs. Runs *after* the reactor is up (see below)."""
            try:
                deferreds = [
                    sem.run(self._run_one, url, job_id) for url, job_id in jobs
                ]
                # consumeErrors=True prevents 'Unhandled error in Deferred'
                # noise; addBoth guarantees _stop runs on success OR failure so
                # the process can never hang waiting on the reactor.
                batch = defer.DeferredList(deferreds, consumeErrors=True)
                batch.addBoth(_stop)
            except Exception:  # noqa: BLE001 — never leave the reactor spinning
                logger.exception("Batch dispatch failed; stopping reactor.")
                _stop()

        # IMPORTANT: dispatch jobs via callWhenRunning rather than before
        # reactor.run(). If every job resolves *synchronously* — e.g. all URLs
        # are invalid or already in the visited store — the DeferredList fires
        # immediately; attaching _stop before the reactor started would run it
        # while reactor.running is still False (a no-op), and reactor.run()
        # would then block forever. callWhenRunning guarantees _stop fires while
        # the reactor is actually running.
        reactor.callWhenRunning(_start)
        reactor.run()  # blocks until _stop() fires

        self._summary.mark_finished()
        logger.info("Batch finished — %s", self._summary.counts())
        return self._summary

    @defer.inlineCallbacks
    def _run_one(self, url: str, job_id: str):  # noqa: D401
        # --- dedup guard ------------------------------------------------------
        if not self._force and self._store.has_visited(url):
            logger.info(
                "[%s] SKIP — already scraped: %s", job_id, normalize_url(url)
            )
            self._summary.add(
                JobResult(url, job_id, "skipped", "already in visited store")
            )
            return

        # --- validation -------------------------------------------------------
        try:
            validated = validate(url, ping=self._ping)
        except URLValidationError as exc:
            logger.error("[%s] INVALID — %s (%s)", job_id, url, exc)
            self._summary.add(JobResult(url, job_id, "invalid", str(exc)))
            return

        # --- crawl ------------------------------------------------------------
        logger.info("[%s] START job — %s", job_id, validated)
        # Create the crawler explicitly so we can read its stats afterwards.
        crawler = self._runner.create_crawler(DocumentSpider)
        try:
            yield self._runner.crawl(
                crawler,
                start_url=validated,
                job_id=job_id,
                file_types=self._file_types,
                profile=self._profile,
            )
            self._store.mark_visited(validated, job_id)
            found, downloaded, size = _read_stats(crawler)
            logger.info(
                "[%s] DONE job — %s (found=%d downloaded=%d bytes=%d)",
                job_id, validated, found, downloaded, size,
            )
            self._summary.add(
                JobResult(
                    validated, job_id, "scraped",
                    files_found=found,
                    files_downloaded=downloaded,
                    bytes_downloaded=size,
                )
            )
        except Exception as exc:  # noqa: BLE001 — report any crawl failure
            logger.error("[%s] ERROR job — %s (%s)", job_id, validated, exc)
            found, downloaded, size = _read_stats(crawler)
            self._summary.add(
                JobResult(
                    validated, job_id, "error", str(exc),
                    files_found=found,
                    files_downloaded=downloaded,
                    bytes_downloaded=size,
                )
            )


def _read_stats(crawler) -> tuple[int, int, int]:
    """Extract (files_found, files_downloaded, bytes_downloaded) from a crawler.

    The DocumentSpider records these under the ``webscraper/*`` keys via the
    Scrapy stats collector; missing keys default to 0.
    """
    try:
        stats = crawler.stats.get_stats()
    except Exception:  # noqa: BLE001 — stats may be unavailable on early failure
        return 0, 0, 0
    return (
        int(stats.get("webscraper/files_found", 0)),
        int(stats.get("webscraper/files_downloaded", 0)),
        int(stats.get("webscraper/bytes_downloaded", 0)),
    )
