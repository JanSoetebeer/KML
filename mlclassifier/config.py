"""
Central, overridable configuration for the classifier.

Everything tuneable lives here so the training and prediction code stays free of
magic numbers. Values can be overridden per-run from the CLI where it matters.
"""

from __future__ import annotations

from pathlib import Path

# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #

# Repo root = parent of the mlclassifier package directory.
REPO_ROOT = Path(__file__).resolve().parents[1]

# Default labelled-data folder: <repo>/modulhandbuecher/{positiv,negativ}/<uni>/*.pdf
DEFAULT_DATA_DIR = REPO_ROOT / "modulhandbuecher"

# Where trained artifacts and the extraction cache are written.
ARTIFACTS_DIR = REPO_ROOT / "mlclassifier" / "artifacts"
DEFAULT_MODEL_PATH = ARTIFACTS_DIR / "module_classifier.joblib"
DEFAULT_CACHE_PATH = ARTIFACTS_DIR / "extraction_cache.jsonl"
DEFAULT_REPORT_PATH = ARTIFACTS_DIR / "training_report.json"

# Folder names that carry the label. Accepts both German spellings.
POSITIVE_DIRNAMES = ("positiv", "positive")
NEGATIVE_DIRNAMES = ("negativ", "negative")

# --------------------------------------------------------------------------- #
# Text extraction
# --------------------------------------------------------------------------- #

# A document whose extracted text is shorter than this (characters, stripped) is
# flagged low-text: likely a scanned/image PDF. It is NOT auto-labelled negative
# (see spec §2) — it gets an extraction_status so training can decide.
MIN_TEXT_CHARS = 200

# Cap how much text we keep per document. Modulhandbücher can be hundreds of
# pages; TF-IDF handles long text fine, but capping keeps the cache and vectoriser
# bounded and avoids one 900-page file dominating. 0 disables the cap.
MAX_TEXT_CHARS = 400_000

# --------------------------------------------------------------------------- #
# Model / features
# --------------------------------------------------------------------------- #

RANDOM_STATE = 42

# Number of cross-validation folds (grouped by university). Capped at run time to
# the number of available groups of the minority class.
CV_SPLITS = 5

# --------------------------------------------------------------------------- #
# Decision thresholds (3-way: positive / review / negative)
#
# These are *defaults*. train.py derives a data-driven upper threshold that hits
# the target recall on validation folds and writes the chosen values into the
# artifact; predict.py reads them back. See spec §9.
# --------------------------------------------------------------------------- #

# Business goal from the spec: prefer high recall — better to review a few extra
# documents than to miss a real Modulhandbuch.
TARGET_RECALL = 0.95

# Fallback thresholds if none are stored in the artifact.
DEFAULT_LOWER_THRESHOLD = 0.20   # score <= lower  -> automatic negative
DEFAULT_UPPER_THRESHOLD = 0.80   # score >= upper  -> automatic positive
                                 # in between       -> manual review
