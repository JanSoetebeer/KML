"""
Feature engineering: two comparable variants (spec §3).

- ``content``  — TF-IDF over the document text only (word + char n-grams).
- ``metadata`` — the above PLUS filename, title and numeric document features.

Both are compared during training. If ``metadata`` is dramatically better, that
is a red flag that the model is reading the filename rather than the document
(spec §3, "Achtung bei Dateiname und URL").

Char n-grams (alongside word n-grams) are deliberate: they are robust to OCR
noise and hyphenation artefacts like ``Modulbeschre1bung`` / ``Lernergebnlsse``
(spec §2).

Everything operates on a pandas DataFrame produced by :func:`records_to_frame`,
so the whole thing composes into one sklearn ColumnTransformer that is fit only
on training folds (no leakage — spec §6).
"""

from __future__ import annotations

import math
import re

import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import FunctionTransformer, StandardScaler

# Typical Modulhandbuch section headings / fields (spec §3). Used only as *soft*
# numeric density features — never as hard rules, since Prüfungsordnungen and
# accreditation reports contain the same words.
_MODULE_TERMS = (
    "modulnummer", "modulbezeichnung", "modulkennung", "modultitel",
    "lernergebnisse", "qualifikationsziele", "lernziele", "kompetenzen",
    "teilnahmevoraussetzung", "prüfungsleistung", "prüfungsform",
    "verwendbarkeit", "arbeitsaufwand", "workload", "lehrform", "lehrveranstaltung",
    "modulverantwortliche", "häufigkeit des angebots", "dauer des moduls",
)
_ECTS_RE = re.compile(r"\b(ects|leistungspunkte|credits?)\b", re.IGNORECASE)
_MODULE_CODE_RE = re.compile(r"\b[A-ZÄÖÜ]{2,}[-_ ]?\d{2,}\b")  # e.g. INF-101, B_AWP25
_DIGIT_RE = re.compile(r"\d")

NUMERIC_FEATURES = [
    "page_count",
    "log_text_length",
    "ects_density",       # ECTS/credit mentions per 1k chars
    "module_term_density",  # module-heading hits per 1k chars
    "module_code_count",  # distinct module-code-like tokens (capped)
    "digit_ratio",        # share of digit characters (module tables are number-heavy)
]


def _numeric_features(text: str, page_count: int, text_length: int) -> dict:
    low = text.lower()
    n = max(len(text), 1)
    per_1k = 1000.0 / n
    ects = len(_ECTS_RE.findall(low))
    term_hits = sum(low.count(t) for t in _MODULE_TERMS)
    codes = min(len(set(_MODULE_CODE_RE.findall(text))), 500)
    digits = len(_DIGIT_RE.findall(text))
    return {
        "page_count": float(page_count),
        "log_text_length": math.log1p(text_length),
        "ects_density": ects * per_1k,
        "module_term_density": term_hits * per_1k,
        "module_code_count": float(codes),
        "digit_ratio": digits / n,
    }


def records_to_frame(records) -> pd.DataFrame:
    """Convert DocRecords (or equivalent dicts) into the model input frame."""
    rows = []
    for r in records:
        get = r.get if isinstance(r, dict) else (lambda k, d=None, _r=r: getattr(_r, k, d))
        text = get("text", "") or ""
        page_count = int(get("page_count", 0) or 0)
        text_length = int(get("text_length", len(text)) or 0)
        row = {
            "text": text,
            "filename": get("filename", "") or "",
            "title": get("title", "") or "",
            **_numeric_features(text, page_count, text_length),
        }
        rows.append(row)
    return pd.DataFrame(rows)


def _text_vectorizers(prefix: str, min_df: int):
    """Word + char TF-IDF over the 'text' column."""
    word = TfidfVectorizer(
        analyzer="word", ngram_range=(1, 2), min_df=min_df,
        sublinear_tf=True, strip_accents="unicode", lowercase=True,
        max_features=60_000,
    )
    char = TfidfVectorizer(
        analyzer="char_wb", ngram_range=(3, 5), min_df=min_df,
        sublinear_tf=True, lowercase=True, max_features=60_000,
    )
    return [(f"{prefix}_word", word, "text"), (f"{prefix}_char", char, "text")]


def build_feature_pipeline(use_metadata: bool, min_df: int = 2) -> ColumnTransformer:
    """
    Build the feature transformer.

    Parameters
    ----------
    use_metadata:
        False → content-only (text TF-IDF). True → also filename, title and
        numeric document features.
    min_df:
        Minimum document frequency for text n-grams. Lowered automatically for
        tiny training folds by the caller if needed.
    """
    transformers = _text_vectorizers("txt", min_df)

    if use_metadata:
        transformers += [
            # Filename as char n-grams: catches 'modulhandbuch'/'modulkatalog'
            # substrings AND their absence — a strong but potentially leaky signal.
            ("fname", TfidfVectorizer(
                analyzer="char_wb", ngram_range=(3, 5), min_df=1, lowercase=True,
            ), "filename"),
            ("title", TfidfVectorizer(
                analyzer="word", ngram_range=(1, 2), min_df=1, lowercase=True,
                strip_accents="unicode",
            ), "title"),
            ("num", Pipeline([
                ("select", FunctionTransformer(
                    lambda df: df[NUMERIC_FEATURES], validate=False,
                )),
                # with_mean=False keeps the rest of the matrix sparse-friendly.
                ("scale", StandardScaler(with_mean=False)),
            ]), NUMERIC_FEATURES),
        ]

    return ColumnTransformer(
        transformers=transformers,
        remainder="drop",
        sparse_threshold=1.0,
    )
