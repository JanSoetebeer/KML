"""
Text extraction → one unified document format for every file type.

Design goal (spec §2): whatever the input file type, produce the *same* dict so
downstream feature building and the model never branch on file type. A failed
extraction is reported via ``extraction_status`` and is **not** silently turned
into an empty/negative document — otherwise the model would learn "little text =
not a Modulhandbuch" (spec §2, §15.5).

Unified record
--------------
    {
        "filename":          "modulhandbuch_informatik.pdf",
        "file_type":         "pdf",
        "title":             "Modulhandbuch Bachelor Informatik" | "",
        "text":              "...",            # possibly truncated to MAX_TEXT_CHARS
        "page_count":        124,
        "text_length":       287423,           # length of full text before truncation
        "ocr_used":          False,
        "extraction_status": "classified" | "empty_document" | "unsupported"
                             | "extraction_failed",
    }

Only PDF extraction is implemented for the baseline (the labelled set is 100%
PDF). DOCX / HTML hooks are present but guarded so the package imports without
those optional dependencies; wiring them in is a drop-in later step.
"""

from __future__ import annotations

import logging
from pathlib import Path

from . import config

logger = logging.getLogger(__name__)

# Extraction status values.
STATUS_OK = "classified"           # text extracted, enough of it
STATUS_EMPTY = "empty_document"    # opened fine but (almost) no text — likely scanned
STATUS_UNSUPPORTED = "unsupported"  # file type we don't extract yet
STATUS_FAILED = "extraction_failed"  # opening/parsing raised


def _empty_record(path: Path, status: str) -> dict:
    return {
        "filename": path.name,
        "file_type": path.suffix.lstrip(".").lower(),
        "title": "",
        "text": "",
        "page_count": 0,
        "text_length": 0,
        "ocr_used": False,
        "extraction_status": status,
    }


def _truncate(text: str) -> str:
    cap = config.MAX_TEXT_CHARS
    if cap and len(text) > cap:
        return text[:cap]
    return text


def extract_pdf(path: Path) -> dict:
    """Extract text + basic structure from a PDF using PyMuPDF (fitz)."""
    import fitz  # imported lazily so the package imports without PyMuPDF

    try:
        doc = fitz.open(path)
    except Exception as exc:  # noqa: BLE001 — any parse error → status, not crash
        logger.warning("PDF open failed for %s: %s", path.name, exc)
        return _empty_record(path, STATUS_FAILED)

    try:
        parts = []
        for page in doc:
            try:
                parts.append(page.get_text())
            except Exception as exc:  # noqa: BLE001 — skip a bad page, keep the rest
                logger.debug("page extract failed in %s: %s", path.name, exc)
        text = "\n".join(parts)
        page_count = doc.page_count
        title = (doc.metadata or {}).get("title") or ""
    finally:
        doc.close()

    text_length = len(text.strip())
    status = STATUS_OK if text_length >= config.MIN_TEXT_CHARS else STATUS_EMPTY

    return {
        "filename": path.name,
        "file_type": "pdf",
        "title": title.strip(),
        "text": _truncate(text),
        "page_count": page_count,
        "text_length": text_length,
        "ocr_used": False,
        "extraction_status": status,
    }


# Map file extension → extractor. Extend here as new types are supported.
_EXTRACTORS = {
    ".pdf": extract_pdf,
}


def extract_document(path: str | Path) -> dict:
    """
    Extract *path* into the unified document record.

    Never raises for a per-file problem: unsupported types and parse failures are
    returned as records with the corresponding ``extraction_status`` so a batch
    run can continue and training can account for them.
    """
    path = Path(path)
    extractor = _EXTRACTORS.get(path.suffix.lower())
    if extractor is None:
        return _empty_record(path, STATUS_UNSUPPORTED)
    try:
        return extractor(path)
    except Exception as exc:  # noqa: BLE001 — defensive: never crash a batch
        logger.warning("Extraction failed for %s: %s", path, exc)
        return _empty_record(path, STATUS_FAILED)
