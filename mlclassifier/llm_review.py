"""
LLM second-stage classifier — resolve the ``needs_review`` band with Claude.

The shipped TF-IDF model judges documents by word frequency, so genuinely
ambiguous handbooks land in the review band (~5,830 docs at upper=0.50). This
tool sends the *actual text* of each review-band document to Claude on Amazon
Bedrock and asks a direct yes/no — recovering true handbooks the TF-IDF model
wasn't sure about and rejecting the false positives, on documents already in S3
(no re-crawl). It's a precision **and** recall lift over the existing scores.

Auth (Bedrock API key)
----------------------
Uses the Anthropic SDK's Bedrock client, which reads AWS credentials from the
standard chain. For a **Bedrock API key**, set two env vars before running::

    export AWS_BEARER_TOKEN_BEDROCK=<your-bedrock-api-key>
    export AWS_REGION=eu-central-1            # a region where the model is enabled

Model & cost
------------
Defaults to Claude Haiku 4.5 (cheapest, ample for classification). Override with
``BEDROCK_MODEL_ID`` (e.g. ``anthropic.claude-sonnet-5`` for higher accuracy at
higher cost). ~5,830 docs × ~2k input tokens ≈ ~12M tokens → a few dollars on
Haiku; more on Sonnet/Opus. Bedrock is partner-priced — see AWS Bedrock pricing.

Usage
-----
    python -m mlclassifier.llm_review \
        --manifest run_full.jsonl \
        --bucket webscraper-output-081757578883 \
        --out llm_reviewed.jsonl

Only ``decision == needs_review`` lines are processed (override with ``--band``).
Output is a JSONL of updated records; merge it into the manifest (new lines win)
before re-running the evaluation to see the recovered handbooks.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

# Load Bedrock creds (AWS_BEARER_TOKEN_BEDROCK / AWS_REGION) from webscraper/.env
# regardless of cwd, plus any .env in the working directory. Best-effort — a
# missing dotenv package OR an unreadable .env (e.g. root-owned 0600 on the
# server, where creds come from the real env anyway) must never crash the tool.
try:
    from dotenv import load_dotenv

    try:
        load_dotenv(Path(__file__).resolve().parents[1] / "webscraper" / ".env")
    except OSError:
        pass
    try:
        load_dotenv()
    except OSError:
        pass
except ImportError:
    pass

logger = logging.getLogger("llm_review")

# Native-Bedrock inference-profile ID for eu-central-1 (Haiku 4.5). The Mantle
# client is NOT used: some AWS orgs deny `bedrock-mantle` via an SCP while still
# allowing native `bedrock:InvokeModel`. Override per region/model with
# BEDROCK_MODEL_ID (e.g. us.anthropic.claude-haiku-4-5-20251001-v1:0).
DEFAULT_MODEL = "eu.anthropic.claude-haiku-4-5-20251001-v1:0"


def _build_client(region: str, verify_ssl: bool = True):
    """Native Anthropic Bedrock client (bedrock:InvokeModel).

    Auth comes from the standard AWS chain, including a Bedrock API key in
    ``AWS_BEARER_TOKEN_BEDROCK``. ``verify_ssl=False`` (env
    ``BEDROCK_VERIFY_SSL=false``) is a *local* escape hatch for a corporate
    TLS-intercepting proxy — leave it True on EC2/Fargate.
    """
    from anthropic import AnthropicBedrock

    if not verify_ssl:
        import httpx2  # the SDK's bundled HTTP client

        return AnthropicBedrock(aws_region=region,
                                http_client=httpx2.Client(verify=False, timeout=60))
    return AnthropicBedrock(aws_region=region)


def _classify(client, model: str, system_prompt: str, filename: str, title: str,
              text: str, max_chars: int) -> dict:
    """One Claude call → parsed verdict dict. Raises on unparseable output."""
    excerpt = text[:max_chars]
    user = (
        f"Filename: {filename}\nTitle: {title or '(none)'}\n\n"
        f"Document text (may be truncated):\n\"\"\"\n{excerpt}\n\"\"\""
    )
    resp = client.messages.create(
        model=model,
        max_tokens=200,
        system=system_prompt,
        messages=[{"role": "user", "content": user}],
    )
    raw = "".join(getattr(b, "text", "") for b in resp.content).strip()
    # Be tolerant of stray prose around the JSON.
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"no JSON in model reply: {raw[:120]!r}")
    return json.loads(raw[start:end + 1])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m mlclassifier.llm_review",
        description="LLM (Claude on Bedrock) second-stage review of a manifest.")
    ap.add_argument("--manifest", required=True, help="review manifest JSONL")
    ap.add_argument("--out", default="llm_reviewed.jsonl", help="output JSONL")
    ap.add_argument("--bucket", default="", help="S3 bucket for s3_key fetches")
    ap.add_argument("--band", default="needs_review",
                    help="only process docs with this decision (default needs_review)")
    ap.add_argument("--spec", default="modulhandbuch",
                    help="classification spec name (see mlclassifier/specs.py). "
                         "Register a new one to reuse this tool for another use case.")
    ap.add_argument("--limit", type=int, default=0, help="cap docs processed (0=all)")
    ap.add_argument("--model", default=os.getenv("BEDROCK_MODEL_ID", DEFAULT_MODEL))
    ap.add_argument("--region", default=os.getenv("AWS_REGION")
                    or os.getenv("AWS_DEFAULT_REGION") or "us-east-1")
    ap.add_argument("--max-chars", type=int, default=8000,
                    help="chars of document text sent to the model (cost control)")
    ap.add_argument("--workers", type=int, default=int(os.getenv("BEDROCK_WORKERS", "12")),
                    help="parallel Bedrock calls (default 12 — cuts a 5-6h run to "
                         "~30min; lower it if you hit Bedrock throttling)")
    ap.add_argument("--no-verify-ssl", action="store_true",
                    default=os.getenv("BEDROCK_VERIFY_SSL", "true").lower() == "false",
                    help="disable TLS verification — LOCAL use only, for a corporate "
                         "intercepting proxy. Never on EC2/Fargate.")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    from mlclassifier.extraction import STATUS_OK, extract_document_bytes
    from mlclassifier.reprocess_ocr import _load_bytes  # shared S3/local fetch
    from mlclassifier.specs import get_spec

    spec = get_spec(args.spec)
    system_prompt = spec.system_prompt()
    logger.info("classification spec: %s", spec.name)

    s3_client = None
    if args.bucket:
        import boto3

        s3_client = boto3.client("s3")

    client = _build_client(args.region, verify_ssl=not args.no_verify_ssl)
    logger.info("Bedrock client ready (region=%s, model=%s, verify_ssl=%s)",
                args.region, args.model, not args.no_verify_ssl)

    records = [json.loads(l) for l in Path(args.manifest).read_text(encoding="utf-8").splitlines() if l.strip()]
    targets = [r for r in records if r.get("decision") == args.band]
    if args.limit:
        targets = targets[: args.limit]
    logger.info("manifest: %d docs, %d in '%s' band to review", len(records), len(targets), args.band)

    from collections import Counter
    from concurrent.futures import ThreadPoolExecutor
    from threading import Lock

    verdicts: Counter = Counter()
    counters = {"pos": 0, "err": 0, "done": 0}
    lock = Lock()  # guards the manifest file, the Counter, and the progress ints

    def _review_one(rec: dict, fh) -> None:
        content = _load_bytes(rec, args.bucket, s3_client)
        if content is None:
            with lock:
                verdicts["no_bytes"] += 1
            return
        doc = extract_document_bytes(content, rec.get("filename", "unknown"))
        if doc.get("extraction_status") != STATUS_OK or not doc.get("text", "").strip():
            with lock:
                verdicts["no_text"] += 1
            return
        try:
            v = _classify(client, args.model, system_prompt, rec.get("filename", ""),
                          doc.get("title", ""), doc["text"], args.max_chars)
        except Exception as exc:  # noqa: BLE001 — one bad doc must not abort the batch
            logger.warning("LLM classify failed for %s: %s", rec.get("filename"), exc)
            with lock:
                counters["err"] += 1
            return
        is_match = bool(v.get("is_match"))
        updated = {
            **rec,
            "decision": "automatic_positive" if is_match else "automatic_negative",
            "is_module_handbook": is_match,   # kept for the existing eval schema
            "llm_is_match": is_match,
            "llm_spec": spec.name,
            "llm_confidence": v.get("confidence"),
            "llm_reason": v.get("reason", ""),
            "llm_model": args.model,
            "llm_reviewed": True,
        }
        line = json.dumps(updated, ensure_ascii=False) + "\n"
        with lock:  # the anthropic/httpx client is thread-safe; the file write isn't
            verdicts["positive" if is_match else "negative"] += 1
            counters["pos"] += int(is_match)
            counters["done"] += 1
            fh.write(line)
            if counters["done"] % 100 == 0:
                logger.info("  … %d/%d  (positive so far: %d)",
                            counters["done"], len(targets), counters["pos"])

    # Parallel Bedrock calls — I/O-bound (S3 fetch + HTTP), so threads scale well.
    with open(args.out, "w", encoding="utf-8") as fh:
        with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
            list(pool.map(lambda r: _review_one(r, fh), targets))

    logger.info("done: %d reviewed → %s", sum(verdicts.values()), dict(verdicts))
    logger.info("recovered as handbooks: %d  |  errors: %d", counters["pos"], counters["err"])
    logger.info("wrote %s (workers=%d)", args.out, args.workers)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
