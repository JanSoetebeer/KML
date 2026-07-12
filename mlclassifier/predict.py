"""
Score documents with a trained model and apply the 3-way decision (spec §9, §13).

    score >= upper_threshold           -> automatic_positive   (review not required)
    score <= lower_threshold           -> automatic_negative    (review not required)
    lower < score < upper_threshold    -> needs_review          (human-in-the-loop)

The output is a rich record (not just a boolean) carrying the score, decision,
model version and extraction status so results are traceable and the uncertain
band can feed active learning (spec §13, §14).
"""

from __future__ import annotations

from pathlib import Path

from . import config
from .extraction import STATUS_OK, extract_document, extract_document_bytes
from .features import records_to_frame
from .pipeline import load_model


class Classifier:
    """A loaded model + its metadata, ready to score documents."""

    def __init__(self, estimator, metadata: dict):
        self.estimator = estimator
        self.metadata = metadata
        self._pos_col = list(estimator.named_steps["clf"].classes_).index(1)
        self.lower = float(metadata.get("lower_threshold", config.DEFAULT_LOWER_THRESHOLD))
        self.upper = float(metadata.get("upper_threshold", config.DEFAULT_UPPER_THRESHOLD))

    # -- scoring ---------------------------------------------------------------

    def score_record(self, doc: dict) -> float:
        """Probability that a unified document record is a Modulhandbuch."""
        frame = records_to_frame([doc])
        return float(self.estimator.predict_proba(frame)[0, self._pos_col])

    def decide(self, score: float) -> str:
        if score >= self.upper:
            return "automatic_positive"
        if score <= self.lower:
            return "automatic_negative"
        return "needs_review"

    def classify_record(self, doc: dict) -> dict:
        """Score an already-extracted unified document record."""
        # An unreadable document is never auto-classified — route it to review so
        # a scanned/failed positive is not silently dropped (spec §2, §15.5).
        if doc.get("extraction_status") != STATUS_OK:
            return self._result(doc, score=None, decision="needs_review")
        score = self.score_record(doc)
        return self._result(doc, score=score, decision=self.decide(score))

    def classify_file(self, path: str | Path) -> dict:
        """Extract *path* and classify it end to end."""
        return self.classify_record(extract_document(path))

    def classify_bytes(self, content: bytes, filename: str) -> dict:
        """Extract in-memory *content* and classify it (used by the scraper)."""
        return self.classify_record(extract_document_bytes(content, filename))

    # -- output shaping --------------------------------------------------------

    def _result(self, doc: dict, score: float | None, decision: str) -> dict:
        is_pos = None if score is None else bool(score >= self.upper)
        return {
            "filename": doc.get("filename", ""),
            "is_module_handbook": is_pos,
            "module_handbook_score": None if score is None else round(score, 4),
            "decision": decision,
            "review_status": "not_required"
            if decision != "needs_review" else "required",
            "extraction_status": doc.get("extraction_status", ""),
            "model_version": self.metadata.get("model_version", ""),
            "thresholds": {"lower": self.lower, "upper": self.upper},
        }


def load_classifier(path: str | Path = config.DEFAULT_MODEL_PATH) -> Classifier:
    """Load a trained artifact into a ready-to-use :class:`Classifier`."""
    estimator, metadata = load_model(path)
    return Classifier(estimator, metadata)


_SHARED: dict[str, Classifier] = {}


def get_shared_classifier(path: str | Path = config.DEFAULT_MODEL_PATH) -> Classifier:
    """
    Return a process-wide cached classifier for *path*.

    The scraper runs many crawl jobs in one process; loading the model once and
    sharing it avoids re-reading the artifact per job. The estimator is only used
    for read-only ``predict_proba`` calls, so sharing it is safe.
    """
    key = str(Path(path).resolve())
    clf = _SHARED.get(key)
    if clf is None:
        clf = load_classifier(path)
        _SHARED[key] = clf
    return clf
