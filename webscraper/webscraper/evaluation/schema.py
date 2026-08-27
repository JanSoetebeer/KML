"""
Data schema for a crawl-run evaluation.

This module defines the *Datenschema* — a set of plain ``@dataclass`` types that
describe, in one place, every metric the evaluation reports. The same
:class:`MetricSet` is computed for every scenario (a named university, or a
segment such as "all private universities"), so numbers are directly comparable
across scenarios.

Layering
--------
``DocumentRecord``   one downloaded document (one manifest line).
``UniversityResult`` all documents of one university + derived per-uni metrics.
``MetricSet``        the comparable metric bundle (used per uni *and* per scenario).
``ScenarioResult``   a named scenario = a filter over universities + its MetricSet
                     + an optional expectation check.
``RunEvaluation``    the whole run: global KPIs, all universities, all scenarios,
                     temporal analysis and throughput analysis.

Everything is stdlib-only and JSON-serialisable via :func:`dataclasses.asdict`,
so the full evaluation can be dumped to ``evaluation_data.json`` and re-loaded or
diffed between runs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# Decision labels emitted by the classifier pipeline (see
# webscraper/pipelines/classification_pipeline.py). Kept here as the single
# source of truth for the evaluation.
DECISION_POSITIVE = "automatic_positive"
DECISION_REVIEW = "needs_review"
DECISION_NEGATIVE = "automatic_negative"
DECISIONS = (DECISION_POSITIVE, DECISION_REVIEW, DECISION_NEGATIVE)


@dataclass
class DocumentRecord:
    """One downloaded document — a single line of the review manifest (JSONL)."""

    job_id: str
    url: str
    hostname: str
    filename: str
    file_type: str
    module_handbook_score: float
    decision: str
    is_module_handbook: bool
    crawled_at: str  # ISO-8601


@dataclass
class MetricSet:
    """The comparable metric bundle. Computed identically for a single university
    and for a whole segment of universities, which is what makes scenarios
    line up in one table.

    Counts are *documents* unless the name says ``unis``. ``*_unique`` collapses
    duplicate ``(hostname, filename)`` pairs (the same handbook reached via
    several pages)."""

    # population
    n_unis: int = 0
    n_unis_with_data: int = 0        # >=1 document downloaded
    n_unis_with_coverage: int = 0    # >=1 positive Modulhandbuch

    # document counts
    docs_total: int = 0
    docs_unique: int = 0
    mh_positive: int = 0
    mh_review: int = 0
    mh_negative: int = 0
    mh_positive_unique: int = 0

    # rates
    coverage_rate: float = 0.0       # n_unis_with_coverage / n_unis
    positive_rate: float = 0.0       # mh_positive / docs_total  (harvest precision proxy)
    review_rate: float = 0.0         # mh_review / docs_total

    # per-university distribution of positive handbooks
    mh_per_uni_mean: float = 0.0
    mh_per_uni_median: float = 0.0
    mh_per_uni_max: int = 0

    # score distribution across all documents
    score_mean: float = 0.0
    score_median: float = 0.0


@dataclass
class UniversityResult:
    """One university: its master-data (from the input list) joined with the
    documents crawled from its registered domain, plus derived metrics."""

    # master data (from the Hochschul-CSV)
    csv_id: str
    name: str
    short_name: str
    uni_type: str          # Universität / Fachhochschule-HAW / Künstlerisch / Verwaltung / ...
    traeger: str           # öffentlich-rechtlich / privat / kirchlich
    bundesland: str
    students: Optional[int]
    founded: Optional[int]
    domain: str
    seed_url: str

    # crawl outcome
    matched: bool = False  # did the crawl produce any document for this domain?
    is_duplicate_domain: bool = False  # another CSV row already owns this domain
    metrics: MetricSet = field(default_factory=MetricSet)

    # timing (from this uni's document timestamps)
    first_seen: Optional[str] = None
    last_seen: Optional[str] = None
    crawl_span_s: float = 0.0

    # temporal vintage of found handbooks (years parsed from filenames)
    year_min: Optional[int] = None
    year_max: Optional[int] = None
    year_hist: dict = field(default_factory=dict)

    # subdomains the documents actually came from
    hostnames: list = field(default_factory=list)


@dataclass
class Expectation:
    """An assertion attached to a named scenario, so the report can show a
    PASS/FAIL badge (e.g. "Nordakademie should yield 0 handbooks")."""

    description: str
    metric: str            # attribute name on MetricSet, e.g. "mh_positive"
    op: str                # one of ==, !=, <, <=, >, >=
    value: float
    passed: Optional[bool] = None
    actual: Optional[float] = None


@dataclass
class ScenarioResult:
    """A named scenario: a filtered set of universities evaluated with the shared
    :class:`MetricSet`. Two flavours:

    * ``kind='segment'`` — a group (e.g. all "kirchlich" universities).
    * ``kind='university'`` — a single spotlighted university (deep dive).
    """

    key: str
    label: str
    kind: str                              # "segment" | "university" | "global"
    dimension: str = ""                    # e.g. "traeger", "uni_type", "size"
    metrics: MetricSet = field(default_factory=MetricSet)
    member_uni_ids: list = field(default_factory=list)
    zero_coverage_uni_ids: list = field(default_factory=list)
    expectation: Optional[Expectation] = None
    note: str = ""


@dataclass
class TemporalAnalysis:
    """How far back the found handbooks go, parsed from filenames."""

    year_hist: dict = field(default_factory=dict)   # year -> count (positives)
    year_min: Optional[int] = None
    year_max: Optional[int] = None
    n_with_year: int = 0
    n_without_year: int = 0
    # documents crawled per wall-clock hour bucket (discovery timeline)
    crawl_timeline: dict = field(default_factory=dict)  # ISO hour -> doc count


@dataclass
class ThroughputAnalysis:
    """Crawler speed, measured from document-download timestamps."""

    run_start: Optional[str] = None
    run_end: Optional[str] = None
    run_span_s: float = 0.0
    docs_total: int = 0
    docs_per_second: float = 0.0
    docs_per_hour: float = 0.0
    positives_per_hour: float = 0.0
    n_jobs: int = 0
    uni_span_median_s: float = 0.0     # median per-university crawl span
    uni_span_mean_s: float = 0.0
    note: str = ""


@dataclass
class RunEvaluation:
    """Top-level container — the complete evaluation of one crawl run."""

    run_id: str
    generated_at: str
    manifest_path: str
    university_csv: str

    # headline numbers
    expected_total: int                # domain estimate of handbooks that *exist*
    global_metrics: MetricSet = field(default_factory=MetricSet)

    universities: list = field(default_factory=list)   # list[UniversityResult]
    scenarios: list = field(default_factory=list)       # list[ScenarioResult]
    temporal: TemporalAnalysis = field(default_factory=TemporalAnalysis)
    throughput: ThroughputAnalysis = field(default_factory=ThroughputAnalysis)

    # bookkeeping
    n_universities_input: int = 0
    n_manifest_records: int = 0
    unmatched_domains: list = field(default_factory=list)  # manifest domains with no CSV uni
    classifier_note: str = ""
