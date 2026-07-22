"""
Turn a labelled folder tree into a clean, deduplicated list of document records.

Expected layout (either nested-by-university, or flat with slug-prefixed names)::

    <data_dir>/
    ├── positiv/
    │   ├── <university_slug>/<name>__<hash>.pdf     # preferred: keeps the group
    │   └── <name>.pdf                               # flat fallback
    └── negativ/
        └── ...

Why the university matters
--------------------------
The train/test split is grouped by university (spec §5, Scenario B) so the model
can't pass by memorising one school's template. We therefore record a ``group``
for every document. Nested layout → the sub-folder is the group. Flat layout →
we fall back to the filename slug before ``__`` (coarser, but better than
per-file).

Deduplication (spec §6)
-----------------------
Exact duplicates (same normalised-text hash) are collapsed to a single record so
the same document can't land in both train and test. A duplicate that spans two
universities is dropped with a log line — it would otherwise leak.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from . import config
from .extraction import STATUS_OK, extract_document

logger = logging.getLogger(__name__)


@dataclass
class DocRecord:
    """One labelled document, ready for feature building."""

    path: str
    label: int                # 1 = Modulhandbuch, 0 = not
    group: str                # university slug — the CV grouping key
    filename: str
    file_type: str
    title: str
    text: str
    page_count: int
    text_length: int
    ocr_used: bool
    extraction_status: str
    doc_hash: str

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)


def normalized_text_hash(text: str) -> str:
    """Stable hash of normalised text — used to detect exact duplicates (spec §6)."""
    normalized = re.sub(r"\s+", " ", text.lower()).strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _label_for_dir(name: str) -> int | None:
    low = name.lower()
    if low in config.POSITIVE_DIRNAMES:
        return 1
    if low in config.NEGATIVE_DIRNAMES:
        return 0
    return None


def _group_for(path: Path, label_dir: Path) -> str:
    """Recover the university slug for *path* under *label_dir*."""
    rel = path.relative_to(label_dir)
    if len(rel.parts) > 1:
        return rel.parts[0]                      # nested: sub-folder is the group
    # Flat fallback: slug before the "__<hash>" suffix, else the bare stem.
    stem = rel.stem
    return stem.split("__", 1)[0] or stem


# --------------------------------------------------------------------------- #
# Extraction cache
# --------------------------------------------------------------------------- #

def _cache_key(path: Path) -> str:
    """Identity of a file for cache invalidation: path + size + mtime."""
    st = path.stat()
    return f"{path.resolve()}|{st.st_size}|{int(st.st_mtime)}"


def _load_cache(cache_path: Path) -> dict[str, dict]:
    if not cache_path.exists():
        return {}
    cache: dict[str, dict] = {}
    with cache_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                cache[entry["_key"]] = entry
            except (json.JSONDecodeError, KeyError):
                continue  # ignore a corrupt cache line rather than fail the run
    return cache


def _write_cache(cache_path: Path, entries: dict[str, dict]) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with cache_path.open("w", encoding="utf-8") as fh:
        for entry in entries.values():
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def iter_labeled_files(data_dir: Path):
    """Yield ``(path, label, label_dir)`` for every file under a positiv/negativ dir."""
    for child in sorted(data_dir.iterdir()):
        if not child.is_dir():
            continue
        label = _label_for_dir(child.name)
        if label is None:
            continue
        for path in sorted(child.rglob("*")):
            if path.is_file() and path.suffix.lower() in {".pdf"}:
                yield path, label, child


def build_dataset(
    data_dir: Path | str = config.DEFAULT_DATA_DIR,
    cache_path: Path | str = config.DEFAULT_CACHE_PATH,
    *,
    force: bool = False,
) -> list[DocRecord]:
    """
    Extract + label every document under *data_dir*, using a text cache.

    Returns deduplicated :class:`DocRecord`s. Set ``force=True`` to ignore the
    cache and re-extract everything.
    """
    data_dir = Path(data_dir)
    cache_path = Path(cache_path)
    if not data_dir.exists():
        raise FileNotFoundError(f"Data directory not found: {data_dir}")

    cache = {} if force else _load_cache(cache_path)
    updated = dict(cache)

    records: list[DocRecord] = []
    n_files = n_extracted = n_cached = 0

    for path, label, label_dir in iter_labeled_files(data_dir):
        n_files += 1
        key = _cache_key(path)
        entry = cache.get(key)
        if entry is None:
            doc = extract_document(path)
            entry = {"_key": key, **doc}
            updated[key] = entry
            n_extracted += 1
            if n_extracted % 50 == 0:
                logger.info("extracted %d files...", n_extracted)
        else:
            n_cached += 1

        text = entry.get("text", "")
        records.append(
            DocRecord(
                path=str(path),
                label=label,
                group=_group_for(path, label_dir),
                filename=entry.get("filename", path.name),
                file_type=entry.get("file_type", "pdf"),
                title=entry.get("title", ""),
                text=text,
                page_count=int(entry.get("page_count", 0)),
                text_length=int(entry.get("text_length", 0)),
                ocr_used=bool(entry.get("ocr_used", False)),
                extraction_status=entry.get("extraction_status", "classified"),
                doc_hash=normalized_text_hash(text) if text else "",
            )
        )

    _write_cache(cache_path, updated)
    logger.info(
        "dataset: %d files (%d newly extracted, %d cached)",
        n_files, n_extracted, n_cached,
    )

    deduped = _deduplicate(records)
    _log_summary(deduped)
    return deduped


def _deduplicate(records: list[DocRecord]) -> list[DocRecord]:
    """Collapse exact-duplicate documents (spec §6). Cross-group dupes are dropped."""
    by_hash: dict[str, DocRecord] = {}
    kept: list[DocRecord] = []
    n_dupe = n_conflict = 0
    for rec in records:
        if not rec.doc_hash:           # empty/failed extraction: keep, can't dedupe
            kept.append(rec)
            continue
        seen = by_hash.get(rec.doc_hash)
        if seen is None:
            by_hash[rec.doc_hash] = rec
            kept.append(rec)
        else:
            n_dupe += 1
            if seen.group != rec.group or seen.label != rec.label:
                n_conflict += 1
                logger.warning(
                    "duplicate content across groups/labels: %s (%s/%s) == %s (%s/%s)",
                    Path(rec.path).name, rec.group, rec.label,
                    Path(seen.path).name, seen.group, seen.label,
                )
    if n_dupe:
        logger.info("dropped %d exact duplicate(s) (%d cross-group/label)", n_dupe, n_conflict)
    return kept


def _log_summary(records: list[DocRecord]) -> None:
    pos = sum(r.label == 1 for r in records)
    neg = sum(r.label == 0 for r in records)
    groups = {r.group for r in records}
    low = sum(r.extraction_status != STATUS_OK for r in records)
    logger.info(
        "records=%d  positive=%d  negative=%d  universities=%d  low-text/failed=%d",
        len(records), pos, neg, len(groups), low,
    )
