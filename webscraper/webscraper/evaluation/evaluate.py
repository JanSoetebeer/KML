"""
Evaluation engine: join a crawl-run manifest with the input university list and
compute every metric defined in :mod:`webscraper.evaluation.schema`.

Inputs
------
* **manifest** — one or more review-manifest ``*.jsonl`` files (as produced by
  ``ClassificationPipeline`` and uploaded to ``s3://<bucket>/manifests/``).
* **university CSV** — the Hochschul-Liste that seeded the run
  (``hs_liste_ready_for_import 1.csv``). Column order is positional; see
  :func:`load_universities`.

The join key is the *registered domain* (last two DNS labels), because the
crawler is domain-scoped: every document of a university comes from that
university's own domain (subdomains included, e.g. ``www-docs.b-tu.de`` →
``b-tu.de``).

Pure stdlib — no pandas / tldextract — so it runs anywhere the scraper runs.
"""

from __future__ import annotations

import csv
import datetime as dt
import json
import re
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable, Optional
from urllib.parse import urlparse

from webscraper.evaluation.schema import (
    DECISION_NEGATIVE,
    DECISION_POSITIVE,
    DECISION_REVIEW,
    Expectation,
    MetricSet,
    RunEvaluation,
    ScenarioResult,
    TemporalAnalysis,
    ThroughputAnalysis,
    UniversityResult,
)

# --------------------------------------------------------------------------- #
# Loading
# --------------------------------------------------------------------------- #

# A handbook filename usually carries the year of its version/PO. Accept plain
# 4-digit years and WS/SS + 2-digit shorthands, clamped to a sane range.
_YEAR_RE = re.compile(r"(?:19|20)\d{2}")
_YEAR_MIN, _YEAR_MAX = 1998, 2027


def registered_domain(hostname: str) -> str:
    """Collapse a hostname to its registered domain (last two labels).

    ``www.student.uni-stuttgart.de`` → ``uni-stuttgart.de``. Good enough for the
    single-level ``.de`` / ``.eu`` TLDs used across the German university list.
    """
    host = (hostname or "").lower().strip().lstrip(".")
    if host.startswith("www."):
        host = host[4:]
    parts = [p for p in host.split(".") if p]
    return ".".join(parts[-2:]) if len(parts) >= 2 else host


def _to_int(value: str) -> Optional[int]:
    value = (value or "").strip().replace(".", "").replace(" ", "")
    return int(value) if value.isdigit() else None


# Coarse buckets used for the "by university type" scenario. The raw CSV labels
# are long; these are the comparable groups.
def normalize_uni_type(raw: str) -> str:
    r = (raw or "").lower()
    if "universit" in r:
        return "Universität"
    if "fachhochschul" in r or "haw" in r:
        return "Fachhochschule / HAW"
    if "künstler" in r or "kunst" in r or "musik" in r:
        return "Künstlerische Hochschule"
    if "verwaltung" in r:
        return "Verwaltungshochschule"
    return "Sonstige"


def normalize_traeger(raw: str) -> str:
    r = (raw or "").lower()
    if "öffentlich" in r or "offentlich" in r:
        return "öffentlich-rechtlich"
    if "kirchlich" in r:
        return "kirchlich"
    if "privat" in r:
        return "privat"
    return "unbekannt"


def load_universities(csv_path: str) -> list[UniversityResult]:
    """Parse the Hochschul-CSV into :class:`UniversityResult` shells (no metrics
    yet). Handles the file's two quirks: some rows are wrapped in an extra layer
    of quotes (parse as a single field → re-parse), and there is no header row.

    Positional columns: 0=id 1=short 2=name 3=type 4=Träger 5=Bundesland
    6=students 7=founded … first ``http*`` cell = seed URL.
    """
    unis: list[UniversityResult] = []
    with open(csv_path, encoding="utf-8", newline="") as fh:
        for raw in csv.reader(fh):
            row = raw
            if len(row) == 1:  # whole line was quoted → unwrap and re-parse
                row = next(csv.reader([row[0]]))
            if len(row) < 6:
                continue
            seed_url = next((c for c in row if c.strip().startswith("http")), "").strip()
            domain = registered_domain(urlparse(seed_url).hostname or "")
            unis.append(
                UniversityResult(
                    csv_id=row[0].strip(),
                    short_name=row[1].strip(),
                    name=row[2].strip(),
                    uni_type=normalize_uni_type(row[3]),
                    traeger=normalize_traeger(row[4]),
                    bundesland=row[5].strip(),
                    students=_to_int(row[6]) if len(row) > 6 else None,
                    founded=_to_int(row[7]) if len(row) > 7 else None,
                    domain=domain,
                    seed_url=seed_url,
                )
            )
    return unis


def load_manifest_records(paths: Iterable[str]) -> list[dict]:
    """Read one or more JSONL manifests into a flat list of dict records."""
    records: list[dict] = []
    for path in paths:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
    return records


def dedup_latest(records: list[dict], key: str = "url") -> list[dict]:
    """De-duplicate records by *key*, keeping the LAST occurrence, order-stable.

    Lets a re-processing pass (OCR / LLM review) be merged over the original run
    by listing its output manifest *after* the run manifest: the updated line for
    a document wins. Records missing the key are always kept (never merged away).
    """
    last_index: dict = {}
    for i, r in enumerate(records):
        k = r.get(key)
        if k:
            last_index[k] = i
    out: list[dict] = []
    for i, r in enumerate(records):
        k = r.get(key)
        if not k or last_index.get(k) == i:
            out.append(r)
    return out


def rescore_decisions(
    records: list[dict], lower: float, upper: float
) -> int:
    """Recompute each record's ``decision`` from its stored score and new
    thresholds — no re-crawl, no re-classify. Mirrors ``Classifier.decide``:
    ``score >= upper`` → positive, ``score <= lower`` → negative, else review.

    This lets the report be regenerated at any threshold on documents that were
    *already downloaded and scored*, so the effect of a threshold change (e.g.
    lowering ``upper`` to recover handbooks stuck in the review band) can be
    measured on real data before it is rolled out to the live crawl via
    ``CLASSIFIER_UPPER_THRESHOLD``. A record with no score (extraction failed)
    keeps ``needs_review`` — the crawl never auto-decides an unreadable file.

    Returns the number of records whose decision changed.
    """
    changed = 0
    for r in records:
        raw = r.get("module_handbook_score")
        if raw is None:
            continue  # unreadable → stays needs_review (as the live pipeline does)
        score = float(raw)
        if score >= upper:
            decision = DECISION_POSITIVE
        elif score <= lower:
            decision = DECISION_NEGATIVE
        else:
            decision = DECISION_REVIEW
        if decision != r.get("decision"):
            changed += 1
        r["decision"] = decision
        r["is_module_handbook"] = score >= upper
    return changed


# --------------------------------------------------------------------------- #
# Metric computation
# --------------------------------------------------------------------------- #


def _parse_years(filename: str) -> list[int]:
    years = [int(y) for y in _YEAR_RE.findall(filename or "")]
    return [y for y in years if _YEAR_MIN <= y <= _YEAR_MAX]


def _metrics_for_unis(unis: list[UniversityResult]) -> MetricSet:
    """Aggregate a comparable :class:`MetricSet` over a set of universities.

    Every scenario in the report goes through this one function, which is what
    guarantees the columns mean the same thing everywhere.
    """
    m = MetricSet(n_unis=len(unis))
    per_uni_positives: list[int] = []
    all_scores: list[float] = []
    for u in unis:
        um = u.metrics
        if u.matched:
            m.n_unis_with_data += 1
        if um.mh_positive > 0:
            m.n_unis_with_coverage += 1
        m.docs_total += um.docs_total
        m.docs_unique += um.docs_unique
        m.mh_positive += um.mh_positive
        m.mh_review += um.mh_review
        m.mh_negative += um.mh_negative
        m.mh_positive_unique += um.mh_positive_unique
        per_uni_positives.append(um.mh_positive)
        # reconstruct score samples weighted by doc count via stored mean is lossy;
        # instead we recompute below from raw docs when available.
        all_scores.extend(getattr(u, "_scores", []))

    if m.n_unis:
        m.coverage_rate = m.n_unis_with_coverage / m.n_unis
    if m.docs_total:
        m.positive_rate = m.mh_positive / m.docs_total
        m.review_rate = m.mh_review / m.docs_total
    if per_uni_positives:
        m.mh_per_uni_mean = statistics.mean(per_uni_positives)
        m.mh_per_uni_median = statistics.median(per_uni_positives)
        m.mh_per_uni_max = max(per_uni_positives)
    if all_scores:
        m.score_mean = statistics.mean(all_scores)
        m.score_median = statistics.median(all_scores)
    return m


def _iso_hour(ts: str) -> str:
    return ts[:13] if ts else ""  # "2026-08-12T13"


def build_evaluation(
    manifest_paths: list[str],
    csv_path: str,
    expected_total: int = 40000,
    run_id: str = "",
    lower: Optional[float] = None,
    upper: Optional[float] = None,
    merge_latest: bool = False,
) -> RunEvaluation:
    """Full pipeline: load → join → per-uni metrics → scenarios → temporal →
    throughput. Returns a fully populated :class:`RunEvaluation`.

    If ``lower``/``upper`` are given, decisions are recomputed from each record's
    stored score at those thresholds (see :func:`rescore_decisions`) — useful for
    what-if evaluation of a threshold change without re-crawling. If
    ``merge_latest`` is set, records are de-duplicated by URL keeping the last
    occurrence, so an OCR/LLM re-processing manifest listed after the run manifest
    overrides it.
    """

    unis = load_universities(csv_path)
    records = load_manifest_records(manifest_paths)
    if merge_latest:
        records = dedup_latest(records, key="url")
    if lower is not None or upper is not None:
        lo = lower if lower is not None else 0.3317
        up = upper if upper is not None else 0.6511
        rescore_decisions(records, lo, up)

    # Group manifest records by registered domain.
    by_domain: dict[str, list[dict]] = defaultdict(list)
    for r in records:
        by_domain[registered_domain(r.get("hostname", ""))].append(r)

    dom_index = {u.domain: u for u in unis if u.domain}
    matched_domains = set()
    seen_domains: set[str] = set()  # first CSV row per domain owns its documents

    # ---- per-university metrics --------------------------------------------
    for u in unis:
        # If an earlier CSV row already used this registered domain, flag the
        # later row as a duplicate so its documents aren't counted twice. Such
        # rows are excluded from the aggregate scenarios below.
        if u.domain:
            if u.domain in seen_domains:
                u.is_duplicate_domain = True
                continue
            seen_domains.add(u.domain)
        docs = by_domain.get(u.domain, [])
        if not docs:
            continue
        matched_domains.add(u.domain)
        u.matched = True

        decisions = Counter(d.get("decision") for d in docs)
        scores = [float(d.get("module_handbook_score") or 0.0) for d in docs]
        unique_keys = {(d.get("hostname"), d.get("filename")) for d in docs}
        pos_unique_keys = {
            (d.get("hostname"), d.get("filename"))
            for d in docs
            if d.get("decision") == DECISION_POSITIVE
        }
        times = sorted(d.get("crawled_at", "") for d in docs if d.get("crawled_at"))
        hostnames = sorted({d.get("hostname", "") for d in docs})

        # temporal vintage from positive handbook filenames
        year_hist: Counter = Counter()
        for d in docs:
            if d.get("decision") == DECISION_POSITIVE:
                yrs = _parse_years(d.get("filename", ""))
                if yrs:
                    year_hist[max(yrs)] += 1  # the newest year in the name = its vintage

        u._scores = scores  # type: ignore[attr-defined]  (used by _metrics_for_unis)
        u.hostnames = hostnames
        um = u.metrics
        um.n_unis = 1
        um.n_unis_with_data = 1
        um.docs_total = len(docs)
        um.docs_unique = len(unique_keys)
        um.mh_positive = decisions.get(DECISION_POSITIVE, 0)
        um.mh_review = decisions.get(DECISION_REVIEW, 0)
        um.mh_negative = decisions.get(DECISION_NEGATIVE, 0)
        um.mh_positive_unique = len(pos_unique_keys)
        um.n_unis_with_coverage = 1 if um.mh_positive > 0 else 0
        um.coverage_rate = float(um.n_unis_with_coverage)
        if um.docs_total:
            um.positive_rate = um.mh_positive / um.docs_total
            um.review_rate = um.mh_review / um.docs_total
        um.mh_per_uni_mean = um.mh_per_uni_median = um.mh_positive
        um.mh_per_uni_max = um.mh_positive
        if scores:
            um.score_mean = statistics.mean(scores)
            um.score_median = statistics.median(scores)
        if times:
            u.first_seen, u.last_seen = times[0], times[-1]
            u.crawl_span_s = _span_seconds(times[0], times[-1])
        if year_hist:
            u.year_min = min(year_hist)
            u.year_max = max(year_hist)
            u.year_hist = dict(sorted(year_hist.items()))

    unmatched = sorted(d for d in by_domain if d not in dom_index)

    ev = RunEvaluation(
        run_id=run_id or (Path(manifest_paths[0]).stem if manifest_paths else ""),
        generated_at=dt.datetime.now(dt.timezone.utc).isoformat(),
        manifest_path=", ".join(manifest_paths),
        university_csv=csv_path,
        expected_total=expected_total,
        universities=unis,
        n_universities_input=len(unis),
        n_manifest_records=len(records),
        unmatched_domains=unmatched,
    )
    # Aggregate metrics operate on distinct-domain universities to avoid
    # double-counting shared domains; deep dives look up specific unis directly.
    distinct = [u for u in unis if not u.is_duplicate_domain]
    ev.global_metrics = _metrics_for_unis(distinct)
    ev.scenarios = _build_scenarios(unis)
    ev.temporal = _build_temporal(records)
    ev.throughput = _build_throughput(records)
    ev.classifier_note = (
        "Decisions from model '{}'. 'needs_review' = uncertain band between the "
        "classifier's lower/upper thresholds; a human reviews those."
    ).format(records[0].get("model_version", "n/a") if records else "n/a")
    # Stash the final (merged + rescored) records for downstream consumers such
    # as the per-uni diagnostics report. Not a dataclass field, so it is dropped
    # by ``dataclasses.asdict`` when the evaluation is serialised to JSON.
    ev._records = records  # type: ignore[attr-defined]
    return ev


# --------------------------------------------------------------------------- #
# Scenarios (the comparable "Szenarien")
# --------------------------------------------------------------------------- #

# Named deep-dive universities (by registered domain) with an expectation each.
# Chosen to span the spectrum the evaluation must probe.
DEEP_DIVES = [
    ("fernuni-hagen.de", "FernUniversität Hagen (größte Uni DE, Fernstudium)", None),
    ("nordakademie.de", "NORDAKADEMIE (erwartet: ~0 online verfügbar)",
     Expectation("Keine / kaum Modulhandbücher online auffindbar", "mh_positive", "<=", 5)),
    ("eh-berlin.de", "Evangelische Hochschule Berlin (kleine kirchliche HS)", None),
    ("fh-wedel.de", "Fachhochschule Wedel (Referenz: einige, aber nicht alle)",
     Expectation("Findet einige Modulhandbücher (>0)", "mh_positive", ">", 0)),
]


def _make_scenario(key, label, kind, dimension, members, expectation=None, note="") -> ScenarioResult:
    metrics = _metrics_for_unis(members)
    zero_cov = [u.csv_id for u in members if u.matched and u.metrics.mh_positive == 0]
    sc = ScenarioResult(
        key=key, label=label, kind=kind, dimension=dimension, metrics=metrics,
        member_uni_ids=[u.csv_id for u in members],
        zero_coverage_uni_ids=zero_cov, note=note,
    )
    if expectation is not None:
        actual = getattr(metrics, expectation.metric, None)
        sc.expectation = Expectation(
            description=expectation.description, metric=expectation.metric,
            op=expectation.op, value=expectation.value,
            actual=actual, passed=_check(actual, expectation.op, expectation.value),
        )
    return sc


def _check(actual, op, value) -> Optional[bool]:
    if actual is None:
        return None
    return {
        "==": actual == value, "!=": actual != value, "<": actual < value,
        "<=": actual <= value, ">": actual > value, ">=": actual >= value,
    }.get(op)


def _build_scenarios(unis: list[UniversityResult]) -> list[ScenarioResult]:
    # For deep-dive lookups, prefer the row that actually owns a domain's data.
    dom_index: dict[str, UniversityResult] = {}
    for u in unis:
        if u.domain and (u.domain not in dom_index or u.matched):
            dom_index[u.domain] = u

    # Aggregate scenarios use distinct-domain universities only.
    unis = [u for u in unis if not u.is_duplicate_domain]
    scenarios: list[ScenarioResult] = []

    # global
    scenarios.append(_make_scenario("all", "Alle Hochschulen", "global", "", unis))

    # by Träger
    for val in ("öffentlich-rechtlich", "privat", "kirchlich"):
        members = [u for u in unis if u.traeger == val]
        if members:
            scenarios.append(_make_scenario(f"traeger:{val}", f"Träger: {val}",
                                            "segment", "traeger", members))
    # by type
    for val in ("Universität", "Fachhochschule / HAW", "Künstlerische Hochschule",
                "Verwaltungshochschule"):
        members = [u for u in unis if u.uni_type == val]
        if members:
            scenarios.append(_make_scenario(f"type:{val}", f"Typ: {val}",
                                            "segment", "uni_type", members))
    # by size bucket
    buckets = [("<1.000", 0, 1000), ("1.000–5.000", 1000, 5000),
               ("5.000–15.000", 5000, 15000), ("15.000–30.000", 15000, 30000),
               (">30.000", 30000, 10**9)]
    for label, lo, hi in buckets:
        members = [u for u in unis if u.students is not None and lo <= u.students < hi]
        if members:
            scenarios.append(_make_scenario(f"size:{label}", f"Größe: {label} Studierende",
                                            "segment", "size", members))
    # by Bundesland
    for land in sorted({u.bundesland for u in unis if u.bundesland}):
        members = [u for u in unis if u.bundesland == land]
        if len(members) >= 3:  # skip mis-parsed single-row artefacts
            scenarios.append(_make_scenario(f"land:{land}", f"Bundesland: {land}",
                                            "segment", "bundesland", members))
    # deep dives (single universities)
    for domain, label, expectation in DEEP_DIVES:
        u = dom_index.get(domain)
        if u:
            scenarios.append(_make_scenario(f"uni:{domain}", label, "university",
                                            "deep_dive", [u], expectation=expectation))
    return scenarios


# --------------------------------------------------------------------------- #
# Temporal & throughput
# --------------------------------------------------------------------------- #


def _span_seconds(a: str, b: str) -> float:
    try:
        return (dt.datetime.fromisoformat(b) - dt.datetime.fromisoformat(a)).total_seconds()
    except Exception:
        return 0.0


def _build_temporal(records: list[dict]) -> TemporalAnalysis:
    t = TemporalAnalysis()
    year_hist: Counter = Counter()
    timeline: Counter = Counter()
    with_year = without_year = 0
    for r in records:
        timeline[_iso_hour(r.get("crawled_at", ""))] += 1
        if r.get("decision") != DECISION_POSITIVE:
            continue
        yrs = _parse_years(r.get("filename", ""))
        if yrs:
            year_hist[max(yrs)] += 1
            with_year += 1
        else:
            without_year += 1
    t.year_hist = dict(sorted(year_hist.items()))
    t.year_min = min(year_hist) if year_hist else None
    t.year_max = max(year_hist) if year_hist else None
    t.n_with_year, t.n_without_year = with_year, without_year
    t.crawl_timeline = dict(sorted(timeline.items()))
    return t


def _build_throughput(records: list[dict]) -> ThroughputAnalysis:
    th = ThroughputAnalysis(docs_total=len(records))
    times = sorted(r.get("crawled_at", "") for r in records if r.get("crawled_at"))
    if not times:
        return th
    th.run_start, th.run_end = times[0], times[-1]
    th.run_span_s = _span_seconds(times[0], times[-1])
    positives = sum(1 for r in records if r.get("decision") == DECISION_POSITIVE)
    if th.run_span_s > 0:
        th.docs_per_second = len(records) / th.run_span_s
        th.docs_per_hour = th.docs_per_second * 3600
        th.positives_per_hour = positives / th.run_span_s * 3600

    # per-job (≈ per-university crawl) spans
    job_times: dict[str, list[str]] = defaultdict(list)
    for r in records:
        if r.get("crawled_at"):
            job_times[r.get("job_id")].append(r["crawled_at"])
    spans = [_span_seconds(min(v), max(v)) for v in job_times.values() if len(v) > 1]
    th.n_jobs = len(job_times)
    if spans:
        th.uni_span_median_s = statistics.median(spans)
        th.uni_span_mean_s = statistics.mean(spans)
    th.note = (
        "Throughput is measured from *downloaded-document* timestamps (the only "
        "per-item time in the manifest), i.e. documents/second — not raw HTTP "
        "pages/second. Wall-clock spans overlap because ~30 domains crawl "
        "concurrently, so run_span is elapsed time, not summed work."
    )
    return th
