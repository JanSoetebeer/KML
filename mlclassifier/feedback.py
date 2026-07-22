"""
Fold human-in-the-loop verdicts back into the training set and retrain (spec §14).

This closes the active-learning loop. During a crawl the scraper's
``ClassificationPipeline`` writes a review manifest; the webapp then lets a
reviewer record a **verdict** (positive / negative) for each surfaced document
and stores those verdicts in a per-run JSONL file that mirrors the manifest:

    output/_review/feedback_<job_id>.jsonl        (local)
    s3://<bucket>/feedback/<job_id>.jsonl         (production)

Each verdict line is self-contained (filename, hostname, saved_path, s3_key,
verdict, reviewer, …), so this module never has to re-join against the manifest.
For every verdict it resolves the document's bytes — from ``saved_path`` on disk
if present, otherwise by downloading ``s3_key`` from the bucket — and copies the
file into::

    modulhandbuecher/<positiv|negativ>/<hostname>/<filename>

using the **human** label, not the model's guess. The hostname stays the group
so the grouped train/test split keeps holding after new data lands. A retrain
then picks up the enlarged corpus.

The verdict field is deliberately model-agnostic: it only ever says "positive"
or "negative", so a future model with a completely different target reuses this
path unchanged — only the meaning of positive/negative differs.
"""

from __future__ import annotations

import json
import logging
import tempfile
from pathlib import Path

from . import config
from .ingest import _copy_into, _label_dirname

logger = logging.getLogger(__name__)

# Default place the webapp / scraper drop review + feedback files locally.
DEFAULT_REVIEW_DIR = config.REPO_ROOT / "webscraper" / "output" / "_review"


# --------------------------------------------------------------------------- #
# Locating feedback files
# --------------------------------------------------------------------------- #

def find_feedback_files(review_dir: Path | str = DEFAULT_REVIEW_DIR) -> list[Path]:
    """All ``feedback_*.jsonl`` files in *review_dir* (newest first)."""
    review_dir = Path(review_dir)
    if not review_dir.is_dir():
        return []
    files = sorted(review_dir.glob("feedback_*.jsonl"), key=lambda p: p.stat().st_mtime)
    return list(reversed(files))


def list_feedback_job_ids_s3(s3_bucket: str, region: str | None = None) -> list[str]:
    """List the job ids that have a feedback file under ``feedback/`` in the bucket."""
    try:
        import boto3

        client = boto3.client("s3", region_name=region)
        job_ids: list[str] = []
        paginator = client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=s3_bucket, Prefix="feedback/"):
            for obj in page.get("Contents", []):
                key = obj["Key"]
                if key.endswith(".jsonl"):
                    job_ids.append(Path(key).stem)  # feedback/<job_id>.jsonl -> <job_id>
        return job_ids
    except Exception as exc:  # noqa: BLE001 — boto3 missing / creds / network
        logger.warning("could not list feedback in s3://%s: %s", s3_bucket, exc)
        return []


def download_feedback_from_s3(
    job_ids: list[str], dest_dir: Path | str, *, s3_bucket: str, region: str | None = None
) -> list[Path]:
    """Download ``feedback/<job_id>.jsonl`` for each id into *dest_dir*."""
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    out: list[Path] = []
    for job_id in job_ids:
        dest = dest_dir / f"feedback_{job_id}.jsonl"
        if _download_s3(s3_bucket, f"feedback/{job_id}.jsonl", dest, region):
            out.append(dest)
        else:
            logger.warning("no feedback in S3 for job %s", job_id)
    return out


# --------------------------------------------------------------------------- #
# Resolving a document's bytes
# --------------------------------------------------------------------------- #

def _download_s3(bucket: str, key: str, dest: Path, region: str | None) -> bool:
    """Download s3://bucket/key to *dest*. Returns True on success."""
    try:
        import boto3
        from botocore.exceptions import ClientError

        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            boto3.client("s3", region_name=region).download_file(bucket, key, str(dest))
            return True
        except ClientError as exc:
            logger.warning("S3 download failed for s3://%s/%s: %s", bucket, key, exc)
            return False
    except Exception as exc:  # noqa: BLE001 — boto3 missing / creds / network
        logger.warning("S3 unavailable (%s); cannot fetch %s", exc, key)
        return False


def _resolve_source(
    entry: dict, *, s3_bucket: str | None, region: str | None, tmp_dir: Path
) -> Path | None:
    """Return a local path to the verdict's document, downloading from S3 if needed."""
    saved = entry.get("saved_path")
    if saved:
        p = Path(saved)
        if p.exists():
            return p
    s3_key = entry.get("s3_key")
    if s3_key and s3_bucket:
        dest = tmp_dir / (entry.get("filename") or Path(s3_key).name)
        if _download_s3(s3_bucket, s3_key, dest, region):
            return dest
    return None


# --------------------------------------------------------------------------- #
# Ingest verdicts
# --------------------------------------------------------------------------- #

def ingest_from_feedback(
    feedback_paths: list[Path | str],
    *,
    data_dir: Path | str = config.DEFAULT_DATA_DIR,
    s3_bucket: str | None = None,
    region: str | None = None,
) -> dict:
    """
    Copy every reviewed document into the training set under its human label.

    Returns a breakdown ``{"positive", "negative", "copied", "skipped", "total"}``.
    A verdict whose file can't be found (missing on disk and not in S3) is
    skipped with a warning rather than aborting the whole batch.
    """
    data_dir = Path(data_dir)
    counts = {"positive": 0, "negative": 0, "copied": 0, "skipped": 0, "total": 0}
    tmp_dir = Path(tempfile.mkdtemp(prefix="mlclf_feedback_"))

    for fpath in feedback_paths:
        fpath = Path(fpath)
        if not fpath.exists():
            logger.warning("feedback file missing: %s", fpath)
            continue
        for line in fpath.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            verdict = str(entry.get("verdict", "")).lower()
            if verdict not in ("positive", "negative"):
                continue
            counts["total"] += 1

            try:
                label_dir = _label_dirname(verdict)
            except ValueError:
                counts["skipped"] += 1
                continue

            src = _resolve_source(entry, s3_bucket=s3_bucket, region=region, tmp_dir=tmp_dir)
            if src is None:
                logger.warning(
                    "cannot locate document for verdict (filename=%s, s3_key=%s)",
                    entry.get("filename"), entry.get("s3_key"),
                )
                counts["skipped"] += 1
                continue

            group = entry.get("hostname") or "unknown"
            if _copy_into(src, label_dir, group, data_dir):
                counts["copied"] += 1
                counts[verdict] += 1
            else:
                counts["skipped"] += 1  # already in the training set

    logger.info(
        "ingested feedback: %d copied (%d pos / %d neg), %d skipped of %d verdict(s)",
        counts["copied"], counts["positive"], counts["negative"],
        counts["skipped"], counts["total"],
    )
    return counts


# --------------------------------------------------------------------------- #
# End-to-end retrain
# --------------------------------------------------------------------------- #

def feedback_retrain(
    *,
    feedback_paths: list[Path | str] | None = None,
    review_dir: Path | str = DEFAULT_REVIEW_DIR,
    job_ids: list[str] | None = None,
    from_s3: bool = False,
    s3_bucket: str | None = None,
    region: str | None = None,
    data_dir: Path | str = config.DEFAULT_DATA_DIR,
    model_path: Path | str = config.DEFAULT_MODEL_PATH,
    cache_path: Path | str = config.DEFAULT_CACHE_PATH,
    do_train: bool = True,
) -> dict:
    """
    Gather verdicts, fold them into the training set, and (optionally) retrain.

    Feedback sources, in order of precedence:
    - explicit ``feedback_paths`` (files), else
    - ``from_s3`` + ``job_ids`` (download from the bucket), else
    - every ``feedback_*.jsonl`` in ``review_dir`` (the local default).
    """
    tmp_dir = Path(tempfile.mkdtemp(prefix="mlclf_fb_dl_"))

    if feedback_paths:
        paths = [Path(p) for p in feedback_paths]
    elif from_s3:
        if not s3_bucket:
            raise ValueError("--from-s3 needs an S3 bucket (--s3-bucket or S3_BUCKET).")
        # No explicit job ids → pull every run that has verdicts in the bucket.
        ids = job_ids or list_feedback_job_ids_s3(s3_bucket, region)
        if not ids:
            logger.warning("no feedback files found in s3://%s/feedback/", s3_bucket)
            return {"ingest": {"total": 0, "copied": 0}, "trained": False, "report": None}
        logger.info("pulling verdicts for %d run(s) from S3", len(ids))
        paths = download_feedback_from_s3(ids, tmp_dir, s3_bucket=s3_bucket, region=region)
    else:
        paths = find_feedback_files(review_dir)

    if not paths:
        logger.warning("no feedback files found — nothing to ingest.")
        return {"ingest": {"total": 0, "copied": 0}, "trained": False, "report": None}

    logger.info("using %d feedback file(s): %s", len(paths), ", ".join(str(p) for p in paths))
    ingest = ingest_from_feedback(
        paths, data_dir=data_dir, s3_bucket=s3_bucket, region=region,
    )

    result = {"ingest": ingest, "trained": False, "report": None}
    if do_train and ingest["copied"] > 0:
        from .train import train
        logger.info("retraining on the enlarged corpus …")
        result["report"] = train(
            data_dir=data_dir, model_path=model_path, cache_path=cache_path,
        )
        result["trained"] = True
    elif do_train:
        logger.info("no new documents were added; skipping retrain.")
    return result
