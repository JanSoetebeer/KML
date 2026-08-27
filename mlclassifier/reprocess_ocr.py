"""
Recover scanned handbooks with OCR — no re-crawl.

In the 411-uni run, 2,074 PDFs extracted as ``empty_document`` (a page image, no
text layer) and were parked in review with no score. This tool re-processes only
those documents: it fetches each PDF (already sitting in S3 / on disk), forces
OCR extraction on, and re-runs the classifier — turning the scanned handbooks
among them into scored positives/negatives without crawling anything again.

Usage
-----
    # from repo root; needs tesseract-ocr (+ deu pack), pytesseract, Pillow
    python -m mlclassifier.reprocess_ocr \
        --manifest run_full.jsonl \
        --bucket webscraper-output-081757578883 \
        --out ocr_reprocessed.jsonl

Each input manifest line with ``extraction_status == empty_document`` is fetched
(local ``saved_path`` first, else ``s3_key`` from ``--bucket``), OCR-extracted,
and re-classified. Output is a JSONL of the updated records (same schema as the
review manifest) plus a summary to stderr. Merge the output into the run manifest
(new lines win) before re-running the evaluation to see the recovered handbooks.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

# Load env (e.g. AWS creds for S3) from webscraper/.env regardless of cwd.
try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[1] / "webscraper" / ".env")
    load_dotenv()
except ImportError:
    pass

logger = logging.getLogger("reprocess_ocr")

_EMPTY = "empty_document"


def _load_bytes(rec: dict, bucket: str, s3_client) -> bytes | None:
    """Fetch a document's bytes: local saved_path if present, else S3 s3_key."""
    saved = rec.get("saved_path", "")
    if saved and Path(saved).is_file():
        return Path(saved).read_bytes()
    key = rec.get("s3_key", "")
    if key and s3_client is not None and bucket:
        try:
            return s3_client.get_object(Bucket=bucket, Key=key)["Body"].read()
        except Exception as exc:  # noqa: BLE001 — one missing object mustn't abort
            logger.warning("S3 fetch failed for %s: %s", key, exc)
    return None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m mlclassifier.reprocess_ocr",
        description="OCR-reprocess empty_document PDFs from a run manifest.")
    ap.add_argument("--manifest", required=True, help="review manifest JSONL")
    ap.add_argument("--out", default="ocr_reprocessed.jsonl", help="output JSONL")
    ap.add_argument("--bucket", default="", help="S3 bucket for s3_key fetches")
    ap.add_argument("--limit", type=int, default=0, help="cap docs processed (0=all)")
    ap.add_argument("--model-path", default="", help="classifier model (default: shipped)")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    # This tool exists to OCR — force the fallback on regardless of the ambient
    # env (extraction reads OCR_ENABLED at call time).
    os.environ["OCR_ENABLED"] = "true"

    from mlclassifier.predict import get_shared_classifier

    clf = get_shared_classifier(args.model_path) if args.model_path else get_shared_classifier()

    s3_client = None
    if args.bucket:
        import boto3

        s3_client = boto3.client("s3")

    records = [json.loads(l) for l in Path(args.manifest).read_text(encoding="utf-8").splitlines() if l.strip()]
    targets = [r for r in records if r.get("extraction_status") == _EMPTY]
    if args.limit:
        targets = targets[: args.limit]
    logger.info("manifest: %d docs, %d empty_document to OCR-reprocess", len(records), len(targets))

    n_text, n_flipped = 0, 0
    from collections import Counter
    new_decisions: Counter = Counter()
    with open(args.out, "w", encoding="utf-8") as fh:
        for i, rec in enumerate(targets, 1):
            content = _load_bytes(rec, args.bucket, s3_client)
            if content is None:
                continue
            result = clf.classify_bytes(content, rec.get("filename", "unknown"))
            recovered = result["extraction_status"] != _EMPTY
            if recovered:
                n_text += 1
            if result["decision"] != rec.get("decision"):
                n_flipped += 1
            new_decisions[result["decision"]] += 1
            updated = {
                **rec,
                "module_handbook_score": result["module_handbook_score"],
                "decision": result["decision"],
                "is_module_handbook": result["is_module_handbook"],
                "extraction_status": result["extraction_status"],
                "ocr_reprocessed": True,
            }
            fh.write(json.dumps(updated, ensure_ascii=False) + "\n")
            if i % 100 == 0:
                logger.info("  … %d/%d processed", i, len(targets))

    logger.info("done: %d processed, %d gained text via OCR, %d changed decision",
                len(targets), n_text, n_flipped)
    logger.info("new decisions among reprocessed: %s", dict(new_decisions))
    logger.info("wrote %s", args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
