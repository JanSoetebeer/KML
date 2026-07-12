"""
Assemble features + classifier into one sklearn Pipeline, and persist it.

The whole preprocessing-plus-model chain is a single Pipeline so that the TF-IDF
vocabulary and scalers are fit *only* on training data inside cross-validation
(spec §6: no pre-processing the whole dataset before the split).

Classifier: L2-regularised logistic regression with balanced class weights
(spec §4). It handles sparse TF-IDF matrices efficiently and outputs calibrated-
enough probabilities for the 3-way threshold decision (spec §9). A linear SVM is
the documented alternative but does not give probabilities out of the box.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import joblib
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline

from . import MODEL_VERSION, config
from .features import build_feature_pipeline


def build_estimator(
    use_metadata: bool,
    *,
    min_df: int = 2,
    C: float = 1.0,
) -> Pipeline:
    """Feature transformer + logistic-regression classifier as one Pipeline."""
    return Pipeline([
        ("features", build_feature_pipeline(use_metadata=use_metadata, min_df=min_df)),
        ("clf", LogisticRegression(
            C=C,
            class_weight="balanced",   # 136:68 imbalance + real-world skew (spec §8)
            max_iter=2000,
            solver="liblinear",        # solid for high-dim sparse binary problems
            random_state=config.RANDOM_STATE,
        )),
    ])


@dataclass
class ModelMetadata:
    """Everything needed to interpret a prediction and trace it (spec §13)."""

    model_version: str = MODEL_VERSION
    variant: str = "metadata"                 # "content" | "metadata"
    lower_threshold: float = config.DEFAULT_LOWER_THRESHOLD
    upper_threshold: float = config.DEFAULT_UPPER_THRESHOLD
    target_recall: float = config.TARGET_RECALL
    trained_at: str = ""
    n_train_docs: int = 0
    n_universities: int = 0
    metrics: dict = field(default_factory=dict)  # cross-validated headline metrics

    def to_dict(self) -> dict:
        return dict(self.__dict__)


def save_model(estimator: Pipeline, metadata: ModelMetadata, path: Path | str) -> Path:
    """Persist estimator + metadata together as one joblib artifact."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({"estimator": estimator, "metadata": metadata.to_dict()}, path)
    return path


def load_model(path: Path | str = config.DEFAULT_MODEL_PATH) -> tuple[Pipeline, dict]:
    """
    Load a saved artifact.

    Note (spec §13): joblib artifacts require a compatible runtime (matching
    scikit-learn / numpy). Load with the same environment used for training.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(
            f"No model at {path}. Train one first: python -m mlclassifier train"
        )
    bundle = joblib.load(path)
    return bundle["estimator"], bundle["metadata"]
