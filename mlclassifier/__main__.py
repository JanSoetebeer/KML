"""
Command-line interface.

    python -m mlclassifier build-dataset    [--data-dir DIR] [--force]
    python -m mlclassifier train            [--data-dir DIR] [--variant content|metadata]
    python -m mlclassifier predict PATH...   [--model FILE] [--json]
    python -m mlclassifier ingest-feedback   [--review-dir DIR] [--from-s3 --job-id ID]
    python -m mlclassifier feedback-retrain  [--review-dir DIR] [--no-train]

``build-dataset`` only extracts + caches text (useful to warm the cache or
inspect the corpus). ``train`` runs the full evaluate-and-save flow. ``predict``
scores one or more files with a saved model. ``ingest-feedback`` folds human
verdicts (from the webapp's review UI) into the training set; ``feedback-retrain``
does that and retrains in one step — the human-in-the-loop closure (spec §14).
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys

from . import config


def _setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%H:%M:%S",
    )


def _cmd_build_dataset(args) -> int:
    from .dataset import build_dataset
    build_dataset(args.data_dir, args.cache, force=args.force)
    return 0


def _cmd_train(args) -> int:
    from .train import train
    report = train(
        data_dir=args.data_dir,
        model_path=args.model,
        cache_path=args.cache,
        save_variant=args.variant,
        force_extract=args.force,
    )
    print("\n=== training summary ===")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


def _cmd_ingest(args) -> int:
    from .ingest import ingest_from_manifest, ingest_paths
    if args.manifest:
        decisions = set(args.decision) if args.decision else None
        n = ingest_from_manifest(
            args.manifest, args.label, data_dir=args.data_dir, decisions=decisions,
        )
    else:
        n = ingest_paths(args.paths, args.label, data_dir=args.data_dir, group=args.group)
    print(f"ingested {n} file(s) into {args.data_dir} as '{args.label}'. "
          f"Retrain with: python -m mlclassifier train")
    return 0


def _cmd_ingest_feedback(args) -> int:
    from .feedback import find_feedback_files, ingest_from_feedback
    paths = args.feedback or [str(p) for p in find_feedback_files(args.review_dir)]
    if not paths:
        print(f"No feedback files found in {args.review_dir}.")
        return 1
    counts = ingest_from_feedback(
        paths, data_dir=args.data_dir, s3_bucket=args.s3_bucket, region=args.region,
    )
    print(json.dumps(counts, indent=2))
    print("Retrain with: python -m mlclassifier train")
    return 0


def _cmd_feedback_retrain(args) -> int:
    from .feedback import feedback_retrain
    result = feedback_retrain(
        feedback_paths=args.feedback,
        review_dir=args.review_dir,
        job_ids=args.job_id,
        from_s3=args.from_s3,
        s3_bucket=args.s3_bucket,
        region=args.region,
        data_dir=args.data_dir,
        model_path=args.model,
        do_train=not args.no_train,
    )
    print("\n=== feedback ingest ===")
    print(json.dumps(result["ingest"], indent=2))
    if result["trained"]:
        print("\n=== retrained model ===")
        print(json.dumps(result["report"], indent=2, ensure_ascii=False))
    else:
        print("\n(model not retrained)")
    return 0


def _cmd_predict(args) -> int:
    from .predict import load_classifier
    clf = load_classifier(args.model)
    results = [clf.classify_file(p) for p in args.paths]
    if args.json:
        print(json.dumps(results, indent=2, ensure_ascii=False))
    else:
        for r in results:
            score = "  n/a" if r["module_handbook_score"] is None else f"{r['module_handbook_score']:.3f}"
            print(f"{score}  {r['decision']:<20}  {r['filename']}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mlclassifier", description=__doc__)
    parser.add_argument("--log-level", default="INFO")
    parser.add_argument("--cache", default=str(config.DEFAULT_CACHE_PATH),
                        help="Extraction cache path (JSONL).")
    sub = parser.add_subparsers(dest="command", required=True)

    p_build = sub.add_parser("build-dataset", help="Extract + cache text only.")
    p_build.add_argument("--data-dir", default=str(config.DEFAULT_DATA_DIR))
    p_build.add_argument("--force", action="store_true", help="Ignore cache; re-extract.")
    p_build.set_defaults(func=_cmd_build_dataset)

    p_train = sub.add_parser("train", help="Train, evaluate and save the model.")
    p_train.add_argument("--data-dir", default=str(config.DEFAULT_DATA_DIR))
    p_train.add_argument("--model", default=str(config.DEFAULT_MODEL_PATH))
    p_train.add_argument("--variant", choices=["content", "metadata"], default=None,
                        help="Force which variant is shipped (default: auto by PR-AUC).")
    p_train.add_argument("--force", action="store_true", help="Ignore cache; re-extract.")
    p_train.set_defaults(func=_cmd_train)

    p_ing = sub.add_parser(
        "ingest", help="Add reviewed scraped files to the training set.")
    p_ing.add_argument("paths", nargs="*", help="PDF file(s) or dir(s) to ingest.")
    p_ing.add_argument("--label", required=True,
                      help="Label for the ingested files: positiv | negativ.")
    p_ing.add_argument("--manifest", default=None,
                      help="Ingest files listed in a crawl review manifest (JSONL).")
    p_ing.add_argument("--decision", action="append", default=None,
                      help="With --manifest: only ingest this model decision "
                           "(repeatable, e.g. --decision needs_review).")
    p_ing.add_argument("--group", default=None,
                      help="Override the university/domain group (else parent folder).")
    p_ing.add_argument("--data-dir", default=str(config.DEFAULT_DATA_DIR))
    p_ing.set_defaults(func=_cmd_ingest)

    # Feedback (human-in-the-loop) ingest + retrain --------------------------
    from .feedback import DEFAULT_REVIEW_DIR

    def _add_feedback_source_args(p):
        p.add_argument("--feedback", action="append", default=None,
                       help="Explicit feedback JSONL file(s) (repeatable). "
                            "Default: every feedback_*.jsonl in --review-dir.")
        p.add_argument("--review-dir", default=str(DEFAULT_REVIEW_DIR),
                       help="Dir the webapp writes feedback_<job>.jsonl into.")
        p.add_argument("--from-s3", action="store_true",
                       help="Pull verdicts from S3. Without --job-id, auto-discovers "
                            "every run under the bucket's feedback/ prefix.")
        p.add_argument("--job-id", action="append", default=None,
                       help="With --from-s3: restrict to this run id (repeatable).")
        p.add_argument("--s3-bucket", default=os.getenv("S3_BUCKET") or None,
                       help="S3 bucket for --from-s3 / fetching docs by s3_key.")
        p.add_argument("--region", default=os.getenv("AWS_REGION")
                       or os.getenv("AWS_DEFAULT_REGION"),
                       help="AWS region for S3 access.")
        p.add_argument("--data-dir", default=str(config.DEFAULT_DATA_DIR))

    p_fbi = sub.add_parser(
        "ingest-feedback",
        help="Copy reviewed documents into the training set by their human label.")
    _add_feedback_source_args(p_fbi)
    p_fbi.set_defaults(func=_cmd_ingest_feedback)

    p_fbr = sub.add_parser(
        "feedback-retrain",
        help="Ingest human verdicts and retrain the model in one step.")
    _add_feedback_source_args(p_fbr)
    p_fbr.add_argument("--model", default=str(config.DEFAULT_MODEL_PATH))
    p_fbr.add_argument("--no-train", action="store_true",
                       help="Only ingest the verdicts; skip retraining.")
    p_fbr.set_defaults(func=_cmd_feedback_retrain)

    p_pred = sub.add_parser("predict", help="Classify one or more files.")
    p_pred.add_argument("paths", nargs="+", help="PDF file(s) to classify.")
    p_pred.add_argument("--model", default=str(config.DEFAULT_MODEL_PATH))
    p_pred.add_argument("--json", action="store_true", help="Emit full JSON records.")
    p_pred.set_defaults(func=_cmd_predict)

    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    _setup_logging(args.log_level)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
