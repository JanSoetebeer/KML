"""
Fold scraped, human-reviewed documents back into the training set (spec §14).

The scraper's ClassificationPipeline writes a **review manifest** (JSONL) for every
crawl — one line per downloaded document with its saved path, hostname, score and
decision. A human confirms the true label for the interesting ones (the model's
``needs_review`` band is the highest-value pool), then ingests them here.

Ingested files are copied into::

    modulhandbuecher/<label>/<hostname>/<filename>

Using the **hostname as the group** mirrors the training layout (one group per
university/domain), so the grouped train/test split keeps working after new data
is added. Retrain afterwards with ``python -m mlclassifier train``.

Two entry points:
- from a manifest (the clean path for scraped data), optionally filtered by the
  model's decision;
- from raw paths/dirs (for ad-hoc additions).
"""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path

from . import config

logger = logging.getLogger(__name__)


def _label_dirname(label: str) -> str:
    low = label.lower()
    if low in config.POSITIVE_DIRNAMES or low in ("1", "pos", "positive", "positiv"):
        return config.POSITIVE_DIRNAMES[0]
    if low in config.NEGATIVE_DIRNAMES or low in ("0", "neg", "negative", "negativ"):
        return config.NEGATIVE_DIRNAMES[0]
    raise ValueError(f"Unknown label {label!r}; use positiv/negativ (or 1/0).")


def _copy_into(src: Path, label_dir: str, group: str, data_dir: Path) -> bool:
    """Copy *src* into data_dir/<label_dir>/<group>/. Returns True if copied."""
    group = group or "unknown"
    dest_dir = data_dir / label_dir / group
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / src.name
    if dest.exists():
        logger.debug("skip (exists): %s", dest)
        return False
    shutil.copy2(src, dest)
    return True


def ingest_from_manifest(
    manifest_path: Path | str,
    label: str,
    *,
    data_dir: Path | str = config.DEFAULT_DATA_DIR,
    decisions: set[str] | None = None,
) -> int:
    """
    Copy files listed in a review manifest into the training set under *label*.

    ``decisions`` optionally restricts to certain model decisions
    (e.g. ``{"needs_review"}``) so you only ingest the band you actually reviewed.
    """
    manifest_path = Path(manifest_path)
    data_dir = Path(data_dir)
    label_dir = _label_dirname(label)

    n = 0
    with manifest_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if decisions and entry.get("decision") not in decisions:
                continue
            src = Path(entry.get("saved_path", ""))
            if not src.exists():
                logger.warning("manifest file missing on disk: %s", src)
                continue
            group = entry.get("hostname") or "unknown"
            if _copy_into(src, label_dir, group, data_dir):
                n += 1
    logger.info("ingested %d file(s) from manifest into %s/%s", n, data_dir.name, label_dir)
    return n


def ingest_paths(
    paths: list[str | Path],
    label: str,
    *,
    data_dir: Path | str = config.DEFAULT_DATA_DIR,
    group: str | None = None,
) -> int:
    """
    Copy raw PDF *paths* (files or directories) into the training set under *label*.

    ``group`` overrides the university/domain group; otherwise each file's parent
    folder name is used.
    """
    data_dir = Path(data_dir)
    label_dir = _label_dirname(label)

    files: list[Path] = []
    for p in paths:
        p = Path(p)
        if p.is_dir():
            files.extend(sorted(p.rglob("*.pdf")))
        elif p.is_file() and p.suffix.lower() == ".pdf":
            files.append(p)

    n = 0
    for src in files:
        g = group or src.parent.name
        if _copy_into(src, label_dir, g, data_dir):
            n += 1
    logger.info("ingested %d file(s) into %s/%s", n, data_dir.name, label_dir)
    return n
