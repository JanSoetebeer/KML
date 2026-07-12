"""
Train + honestly evaluate the Modulhandbuch classifier.

Pipeline (spec §5–§9):

1. Build the deduplicated dataset (grouped by university).
2. For each feature variant ("content" only vs "content + metadata"): run
   StratifiedGroupKFold so no university is in both train and test (Scenario B,
   the hard/important test — spec §5). Collect out-of-fold (OOF) probabilities.
3. Score with recall-focused metrics: precision / recall / F1 / F2 / PR-AUC
   (average precision) / ROC-AUC + confusion matrix (spec §8).
4. Derive the 3-way decision thresholds from the OOF scores, targeting the
   business recall goal (spec §9). Never assume 0.5.
5. Refit the chosen variant on ALL data and persist it with its metrics and
   thresholds embedded (spec §13).

Comparing the two variants tells us whether the model reads the *document* or
just the *filename* (spec §3).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from sklearn.base import clone
from sklearn.metrics import (
    average_precision_score,
    confusion_matrix,
    fbeta_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import StratifiedGroupKFold

from . import config
from .dataset import DocRecord, build_dataset
from .features import records_to_frame
from .pipeline import ModelMetadata, build_estimator, save_model

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Threshold helpers (spec §9)
# --------------------------------------------------------------------------- #

def threshold_for_recall(y_true, scores, target_recall: float) -> float:
    """
    Highest score threshold whose recall is still >= *target_recall*.

    Predicting positive for ``score >= t`` at this t catches the target share of
    real Modulhandbücher while being as selective as possible.
    """
    order = np.argsort(scores)[::-1]          # high score -> low
    y_sorted = np.asarray(y_true)[order]
    s_sorted = np.asarray(scores)[order]
    total_pos = max(int(y_sorted.sum()), 1)
    tp = 0
    best = float(s_sorted[-1]) if len(s_sorted) else 0.0
    for score, y in zip(s_sorted, y_sorted):
        tp += int(y == 1)
        if tp / total_pos >= target_recall:
            best = float(score)
            break
    return best


def threshold_for_precision(y_true, scores, target_precision: float) -> float | None:
    """Lowest threshold whose precision is >= *target_precision* (for auto-positive)."""
    y = np.asarray(y_true)
    s = np.asarray(scores)
    best_t = None
    for t in np.unique(s)[::-1]:
        pred = s >= t
        if pred.sum() == 0:
            continue
        prec = precision_score(y, pred, zero_division=0)
        if prec >= target_precision:
            best_t = float(t)
        else:
            # precision generally falls as t drops; stop once we lose the target
            if best_t is not None:
                break
    return best_t


# --------------------------------------------------------------------------- #
# Cross-validated evaluation
# --------------------------------------------------------------------------- #

@dataclass
class VariantResult:
    variant: str
    oof_scores: np.ndarray
    y_true: np.ndarray
    metrics: dict
    lower_threshold: float
    upper_threshold: float


def _metrics_at(y_true, scores, threshold: float) -> dict:
    pred = (np.asarray(scores) >= threshold).astype(int)
    tn, fp, fn, tp = confusion_matrix(y_true, pred, labels=[0, 1]).ravel()
    return {
        "threshold": round(float(threshold), 4),
        "precision": round(precision_score(y_true, pred, zero_division=0), 4),
        "recall": round(recall_score(y_true, pred, zero_division=0), 4),
        "f1": round(fbeta_score(y_true, pred, beta=1, zero_division=0), 4),
        "f2": round(fbeta_score(y_true, pred, beta=2, zero_division=0), 4),
        "confusion_matrix": {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)},
    }


def evaluate_variant(
    variant: str,
    frame,
    y,
    groups,
    *,
    n_splits: int,
    min_df: int,
) -> VariantResult:
    """Run grouped CV for one feature variant and collect OOF probabilities."""
    use_metadata = variant == "metadata"
    cv = StratifiedGroupKFold(n_splits=n_splits, shuffle=True,
                              random_state=config.RANDOM_STATE)

    oof = np.full(len(y), np.nan)
    for fold, (tr, te) in enumerate(cv.split(frame, y, groups)):
        est = clone(build_estimator(use_metadata=use_metadata, min_df=min_df))
        est.fit(frame.iloc[tr], y[tr])
        pos_col = list(est.named_steps["clf"].classes_).index(1)
        oof[te] = est.predict_proba(frame.iloc[te])[:, pos_col]
        logger.info("  [%s] fold %d/%d: train=%d test=%d",
                    variant, fold + 1, n_splits, len(tr), len(te))

    assert not np.isnan(oof).any(), "some samples were never in a test fold"

    ap = round(average_precision_score(y, oof), 4)
    roc = round(roc_auc_score(y, oof), 4)
    lower = threshold_for_recall(y, oof, config.TARGET_RECALL)
    upper = threshold_for_precision(y, oof, target_precision=0.95)
    if upper is None or upper < lower:
        upper = max(lower, config.DEFAULT_UPPER_THRESHOLD)

    metrics = {
        "average_precision": ap,          # PR-AUC — headline for imbalanced data
        "roc_auc": roc,
        "n_docs": int(len(y)),
        "n_positive": int(y.sum()),
        "at_recall_target": _metrics_at(y, oof, lower),
        "at_0.5": _metrics_at(y, oof, 0.5),
    }
    logger.info(
        "[%s] PR-AUC=%.3f ROC-AUC=%.3f | @recall-target: P=%.3f R=%.3f F2=%.3f (t=%.3f)",
        variant, ap, roc,
        metrics["at_recall_target"]["precision"],
        metrics["at_recall_target"]["recall"],
        metrics["at_recall_target"]["f2"],
        lower,
    )
    return VariantResult(variant, oof, np.asarray(y), metrics, lower, upper)


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #

def train(
    data_dir: Path | str = config.DEFAULT_DATA_DIR,
    *,
    model_path: Path | str = config.DEFAULT_MODEL_PATH,
    cache_path: Path | str = config.DEFAULT_CACHE_PATH,
    report_path: Path | str = config.DEFAULT_REPORT_PATH,
    save_variant: str | None = None,
    force_extract: bool = False,
) -> dict:
    """Train, evaluate both variants, and persist the chosen model + report."""
    records: list[DocRecord] = build_dataset(data_dir, cache_path, force=force_extract)
    if len(records) < 10:
        raise ValueError(f"Too few documents to train ({len(records)}).")

    frame = records_to_frame(records)
    y = np.array([r.label for r in records])
    groups = np.array([r.group for r in records])

    n_groups = len(set(groups))
    # Need >= n_splits groups; also want both classes present across folds.
    n_splits = max(2, min(config.CV_SPLITS, n_groups,
                          int(y.sum()), int((y == 0).sum())))
    logger.info("CV: StratifiedGroupKFold, %d splits over %d universities", n_splits, n_groups)

    results: dict[str, VariantResult] = {}
    for variant in ("content", "metadata"):
        logger.info("=== evaluating variant: %s ===", variant)
        results[variant] = evaluate_variant(
            variant, frame, y, groups, n_splits=n_splits, min_df=2,
        )

    # Choose which variant to ship. Default: better OOF PR-AUC, but prefer the
    # less leak-prone 'content' model on a near-tie (spec §3).
    if save_variant is None:
        ap_c = results["content"].metrics["average_precision"]
        ap_m = results["metadata"].metrics["average_precision"]
        save_variant = "metadata" if ap_m > ap_c + 0.02 else "content"
        _warn_if_leaky(ap_c, ap_m)
    chosen = results[save_variant]
    logger.info("shipping variant: %s", save_variant)

    # Refit on ALL data for the deployed model.
    final = build_estimator(use_metadata=(save_variant == "metadata"), min_df=2)
    final.fit(frame, y)

    metadata = ModelMetadata(
        variant=save_variant,
        lower_threshold=round(chosen.lower_threshold, 4),
        upper_threshold=round(chosen.upper_threshold, 4),
        target_recall=config.TARGET_RECALL,
        trained_at=datetime.now(timezone.utc).isoformat(),
        n_train_docs=len(records),
        n_universities=n_groups,
        metrics=chosen.metrics,
    )
    saved = save_model(final, metadata, model_path)
    logger.info("saved model -> %s", saved)

    report = {
        "model_version": metadata.model_version,
        "shipped_variant": save_variant,
        "thresholds": {"lower": metadata.lower_threshold, "upper": metadata.upper_threshold},
        "n_docs": len(records),
        "n_universities": n_groups,
        "n_positive": int(y.sum()),
        "n_negative": int((y == 0).sum()),
        "variants": {v: r.metrics for v, r in results.items()},
        "trained_at": metadata.trained_at,
    }
    report_path = Path(report_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("wrote report -> %s", report_path)
    return report


def _warn_if_leaky(ap_content: float, ap_metadata: float) -> None:
    if ap_metadata > ap_content + 0.10:
        logger.warning(
            "metadata variant is much stronger than content-only "
            "(PR-AUC %.3f vs %.3f). Check the model isn't just reading the "
            "filename rather than the document (spec §3).",
            ap_metadata, ap_content,
        )
