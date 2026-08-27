"""
CLI: build the evaluation and write an HTML report + a JSON data dump.

Usage
-----
    python -m webscraper.evaluation \
        --manifest run_full.jsonl [run_other.jsonl ...] \
        --csv "hs_liste_ready_for_import 1.csv" \
        --expected-total 40000 \
        --out-html evaluation_report.html \
        --out-json evaluation_data.json

The manifest(s) are the review manifests produced by the crawl and uploaded to
``s3://<bucket>/manifests/<batch_id>.jsonl``. Download with::

    aws s3 cp s3://webscraper-output-<acct>/manifests/<id>.jsonl run_full.jsonl
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from pathlib import Path

from webscraper.evaluation.evaluate import build_evaluation
from webscraper.evaluation.report import render_html


def _json_default(o):
    # UniversityResult carries a private _scores list; drop transient underscores.
    if dataclasses.is_dataclass(o):
        return {k: v for k, v in dataclasses.asdict(o).items() if not k.startswith("_")}
    return str(o)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m webscraper.evaluation",
                                 description="Evaluate a Modulhandbuch crawl run.")
    ap.add_argument("--manifest", nargs="+", required=True,
                    help="one or more review-manifest JSONL files")
    ap.add_argument("--csv", required=True, help="university seed list (Hochschul-CSV)")
    ap.add_argument("--expected-total", type=int, default=40000,
                    help="domain estimate of handbooks that exist (recall reference)")
    ap.add_argument("--run-id", default="", help="label for the report header")
    ap.add_argument("--lower", type=float, default=None,
                    help="override the classifier's LOWER threshold: recompute "
                         "decisions from stored scores (what-if, no re-crawl)")
    ap.add_argument("--upper", type=float, default=None,
                    help="override the classifier's UPPER threshold: docs scoring "
                         ">= this become positive. Lower it to recover handbooks "
                         "stuck in the review band (model default 0.6511).")
    ap.add_argument("--merge-latest", action="store_true",
                    help="de-dup records by URL keeping the last — list an OCR/LLM "
                         "re-processing manifest AFTER the run manifest to override it")
    ap.add_argument("--out-html", default="evaluation_report.html")
    ap.add_argument("--out-json", default="evaluation_data.json")
    args = ap.parse_args(argv)

    for p in args.manifest + [args.csv]:
        if not Path(p).exists():
            print(f"error: file not found: {p}", file=sys.stderr)
            return 2

    print(f"Loading {len(args.manifest)} manifest(s) + {args.csv} …", file=sys.stderr)
    if args.lower is not None or args.upper is not None:
        print(f"  re-scoring decisions at lower={args.lower} upper={args.upper} "
              f"(what-if; unset falls back to model default)", file=sys.stderr)
    ev = build_evaluation(args.manifest, args.csv,
                          expected_total=args.expected_total, run_id=args.run_id,
                          lower=args.lower, upper=args.upper,
                          merge_latest=args.merge_latest)

    g = ev.global_metrics
    print(f"  universities: {ev.n_universities_input}  |  documents: {ev.n_manifest_records}",
          file=sys.stderr)
    print(f"  MH positive: {g.mh_positive}  review: {g.mh_review}  "
          f"coverage: {g.n_unis_with_coverage}/{g.n_unis}", file=sys.stderr)

    Path(args.out_html).write_text(render_html(ev), encoding="utf-8")
    Path(args.out_json).write_text(
        json.dumps(dataclasses.asdict(ev), ensure_ascii=False, indent=2,
                   default=_json_default),
        encoding="utf-8")
    print(f"Wrote {args.out_html} and {args.out_json}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
