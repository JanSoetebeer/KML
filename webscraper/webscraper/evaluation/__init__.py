"""Crawl-run evaluation: join a review manifest with the input university list
and produce a comparable-metrics report (data schema + HTML)."""

from webscraper.evaluation.evaluate import build_evaluation
from webscraper.evaluation.report import render_html

__all__ = ["build_evaluation", "render_html"]
