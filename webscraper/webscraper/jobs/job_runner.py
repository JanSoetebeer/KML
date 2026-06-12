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


@dataclass
class BatchSummary:
    """Aggregate outcome of a batch of jobs."""

    results: list = field(default_factory=list)

    def add(self, result: JobResult) -> None:
        self.results.append(result)

    def counts(self) -> dict:
        out: dict = {}
        for r in self.results:
            out[r.status] = out.get(r.status, 0) + 1
        return out


class JobRunner:
    """Run a batch of URL jobs with a concurrency cap and dedup guard."""

    def __init__(
        self,
        settings,
        visited_store: BaseVisitedStore,
        max_concurrent: int = 10,
        ping: bool = True,
        force: bool = False,
    ):
        self._settings = settings
        self._store = visited_store
        self._max_concurrent = max(1, int(max_concurrent))
        self._ping = ping
        self._force = force
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

        @defer.inlineCallbacks
        def _orchestrate():
            deferreds = []
            for url, job_id in jobs:
                deferreds.append(sem.run(self._run_one, url, job_id))
            yield defer.DeferredList(deferreds)
            reactor.stop()

        _orchestrate()
        reactor.run()  # blocks until reactor.stop()

        logger.info("Batch finished — %s", self._summary.counts())
        return self._summary

    @defer.inlineCallbacks
    def _run_one(self, url: str, job_id: str):
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
        try:
            yield self._runner.crawl(
                DocumentSpider, start_url=validated, job_id=job_id
            )
            self._store.mark_visited(validated, job_id)
            logger.info("[%s] DONE job — %s", job_id, validated)
            self._summary.add(JobResult(validated, job_id, "scraped"))
        except Exception as exc:  # noqa: BLE001 — report any crawl failure
            logger.error("[%s] ERROR job — %s (%s)", job_id, validated, exc)
            self._summary.add(JobResult(validated, job_id, "error", str(exc)))
