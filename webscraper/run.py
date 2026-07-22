"""
CLI entrypoint for the webscraper.

Each URL is run as its own job (its own spider + job_id). Up to --max-jobs
jobs run concurrently (default from settings.MAX_CONCURRENT_JOBS = 10).
Already-scraped URLs are skipped via the persistent visited store unless
--force is given.

Usage
-----
    python run.py <url> [<url> ...] [options]
    python run.py --urls-file urls.txt [options]

Options
-------
    --urls-file FILE   Read URLs (one per line, '#' comments allowed) from FILE.
    --max-jobs N       Max concurrent jobs (default: settings value, 10).
    --force            Re-scrape URLs even if already in the visited store.
    --log-level LEVEL  DEBUG | INFO | WARNING | ERROR (default INFO).
    --no-ping          Skip the reachability probe during URL validation.

Examples
--------
    python run.py https://example.com/docs
    python run.py https://a.com https://b.com https://c.com --max-jobs 3
    python run.py --urls-file urls.txt --force
"""

import argparse
import json
import logging
import os
import sys
import uuid
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Marker prefixing the JSON run summary printed to stdout (parsed by callers).
SUMMARY_MARKER = "__SCRAPE_SUMMARY__"

os.environ.setdefault("SCRAPY_SETTINGS_MODULE", "webscraper.settings")

from scrapy.utils.project import get_project_settings

from webscraper.jobs.job_runner import JobRunner
from webscraper.state.visited_store import build_visited_store
from webscraper.utils.logging_config import configure as configure_logging


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Webscraper — download documents from one or more URLs."
    )
    parser.add_argument(
        "urls",
        nargs="*",
        help="One or more seed URLs to scrape (http/https).",
    )
    parser.add_argument(
        "--urls-file",
        default=None,
        help="Path to a file with one URL per line ('#' comments allowed).",
    )
    parser.add_argument(
        "--max-jobs",
        type=int,
        default=None,
        help="Max concurrent jobs (default: settings.MAX_CONCURRENT_JOBS).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-scrape URLs even if already recorded in the visited store.",
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
        help="Skip the reachability probe during URL validation.",
    )
    parser.add_argument(
        "--file-types",
        default=None,
        help="Comma-separated file extensions to download (e.g. 'pdf,docx,png'). "
        "Defaults to the spider's built-in set if omitted.",
    )
    parser.add_argument(
        "--batch-id",
        default=None,
        help="Correlation id for this run. Used to name the classification review "
        "manifest so a caller (webapp/Lambda) can fetch this run's results.",
    )
    return parser.parse_args(argv)


def _parse_file_types(value) -> list[str] | None:
    """Turn a comma-separated string into a list of extensions, or None."""
    if not value:
        return None
    parts = [p.strip() for p in str(value).split(",") if p.strip()]
    return parts or None


def _collect_urls(args: argparse.Namespace) -> list[str]:
    """Merge positional URLs and --urls-file into a deduplicated, ordered list.

    ``--urls-file`` may be ``.csv`` (column-aware — picks the URL column, e.g.
    ``Home Page``/``final_url``), ``.html``, or a plain ``.txt`` list.
    """
    from webscraper.utils.url_sources import (
        extract_urls_from_csv_text,
        extract_urls_from_html_text,
        extract_urls_from_text_lines,
    )

    urls: list[str] = list(args.urls)
    if args.urls_file:
        file_path = Path(args.urls_file)
        raw = file_path.read_text(encoding="utf-8-sig")
        suffix = file_path.suffix.lower()
        if suffix == ".csv":
            urls += extract_urls_from_csv_text(raw)
        elif suffix in (".html", ".htm"):
            urls += extract_urls_from_html_text(raw)
        else:
            urls += extract_urls_from_text_lines(raw)
    # Preserve order while dropping duplicates
    seen: set[str] = set()
    ordered: list[str] = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            ordered.append(u)
    return ordered


def run_batch(
    urls: list[str],
    log_level: str = "INFO",
    max_jobs: int | None = None,
    ping: bool = True,
    force: bool = False,
    batch_id: str | None = None,
    file_types=None,
) -> int:
    """
    Run a batch of URLs as concurrent jobs.

    Returns
    -------
    int
        Exit code: 0 if no job errored, 1 if no URLs supplied,
        2 if one or more jobs errored.
    """
    batch_id = batch_id or uuid.uuid4().hex
    # Exposed to the crawl process (pipelines) so the classification manifest can
    # be keyed by this run's id — the webapp/Lambda fetch results by the same id.
    os.environ["SCRAPE_BATCH_ID"] = batch_id
    configure_logging(job_id=batch_id, level=log_level)
    logger = logging.getLogger(__name__)

    if not urls:
        logger.error("No URLs supplied. Provide URLs or --urls-file.")
        return 1

    logger.info("=== webscraper batch started  batch_id=%s ===", batch_id)

    settings = get_project_settings()
    settings.set("LOG_LEVEL", log_level)

    if max_jobs is None:
        max_jobs = settings.getint("MAX_CONCURRENT_JOBS", 10)

    store = build_visited_store(settings)

    # One job_id per URL
    jobs = [(url, uuid.uuid4().hex) for url in urls]

    runner = JobRunner(
        settings=settings,
        visited_store=store,
        max_concurrent=max_jobs,
        ping=ping,
        force=force,
        file_types=file_types,
    )
    summary = runner.run(jobs)

    counts = summary.counts()
    logger.info("=== webscraper batch finished  batch_id=%s  %s ===", batch_id, counts)

    # Emit a machine-readable summary on stdout so callers (Lambda handler /
    # webapp) can surface a results dashboard. The marker lets them locate this
    # single line amongst the log output.
    print(SUMMARY_MARKER + " " + json.dumps(summary.to_dict()), flush=True)

    return 2 if counts.get("error", 0) else 0


def run(
    url: str,
    job_id: str,
    log_level: str = "INFO",
    ping: bool = True,
    file_types=None,
) -> int:
    """
    Single-URL entry point (used by the AWS Lambda handler).

    Thin wrapper around :func:`run_batch` for one URL so the CLI and Lambda
    share the same job-running code path.
    """
    return run_batch(
        urls=[url],
        log_level=log_level,
        max_jobs=1,
        ping=ping,
        batch_id=job_id,
        file_types=file_types,
    )


def main(argv=None) -> None:
    args = parse_args(argv)
    urls = _collect_urls(args)
    exit_code = run_batch(
        urls=urls,
        log_level=args.log_level,
        max_jobs=args.max_jobs,
        ping=not args.no_ping,
        force=args.force,
        batch_id=args.batch_id,
        file_types=_parse_file_types(args.file_types),
    )
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
