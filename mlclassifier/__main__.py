"""
Command-line interface.

    python -m mlclassifier build-dataset [--data-dir DIR] [--force]
    python -m mlclassifier train         [--data-dir DIR] [--variant content|metadata]
    python -m mlclassifier predict PATH... [--model FILE] [--json]

``build-dataset`` only extracts + caches text (useful to warm the cache or
inspect the corpus). ``train`` runs the full evaluate-and-save flow. ``predict``
scores one or more files with a saved model.
"""

from __future__ import annotations

import argparse
import json
import logging
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
