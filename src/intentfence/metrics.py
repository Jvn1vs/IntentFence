from __future__ import annotations

from typing import Any

import numpy as np
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    brier_score_loss,
    classification_report,
    confusion_matrix,
    log_loss,
    roc_auc_score,
)

from intentfence.constants import RISK_LABELS


def softmax(logits: np.ndarray) -> np.ndarray:
    logits = np.asarray(logits, dtype=np.float64)
    shifted = logits - np.max(logits, axis=1, keepdims=True)
    exponentials = np.exp(shifted)
    return exponentials / exponentials.sum(axis=1, keepdims=True)


def expected_calibration_error(
    probabilities: np.ndarray, labels: np.ndarray, n_bins: int = 15
) -> float:
    confidences = probabilities.max(axis=1)
    predictions = probabilities.argmax(axis=1)
    correctness = predictions == labels
    boundaries = np.linspace(0.0, 1.0, n_bins + 1)
    error = 0.0
    for lower, upper in zip(boundaries[:-1], boundaries[1:], strict=True):
        mask = (confidences > lower) & (confidences <= upper)
        if np.any(mask):
            error += np.mean(mask) * abs(np.mean(correctness[mask]) - np.mean(confidences[mask]))
    return float(error)


def multiclass_brier(probabilities: np.ndarray, labels: np.ndarray) -> float:
    one_hot = np.eye(probabilities.shape[1])[labels]
    return float(np.mean(np.sum((probabilities - one_hot) ** 2, axis=1)))


def threshold_at_fpr(
    labels: np.ndarray,
    scores: np.ndarray,
    target_fpr: float = 0.01,
) -> float:
    """Conservative empirical threshold chosen from benign scores only."""

    labels = np.asarray(labels, dtype=int)
    scores = np.asarray(scores, dtype=float)
    benign_scores = np.sort(scores[labels == 0])
    if not len(benign_scores):
        raise ValueError("At least one benign sample is required to choose an FPR threshold")
    if not 0 <= target_fpr < 1:
        raise ValueError("target_fpr must be in [0, 1)")
    allowed_false_positives = int(np.floor(target_fpr * len(benign_scores)))
    index = max(0, len(benign_scores) - allowed_false_positives - 1)
    threshold = float(np.nextafter(benign_scores[index], np.inf))
    return min(threshold, 1.0)


def binary_operating_point(
    labels: np.ndarray, scores: np.ndarray, threshold: float
) -> dict[str, float | int]:
    labels = np.asarray(labels, dtype=int)
    predictions = (np.asarray(scores) >= threshold).astype(int)
    tn, fp, fn, tp = confusion_matrix(labels, predictions, labels=[0, 1]).ravel()
    return {
        "threshold": float(threshold),
        "tn": int(tn),
        "fp": int(fp),
        "fn": int(fn),
        "tp": int(tp),
        "fpr": float(fp / (fp + tn)) if fp + tn else 0.0,
        "tpr": float(tp / (tp + fn)) if tp + fn else 0.0,
        "precision": float(tp / (tp + fp)) if tp + fp else 0.0,
    }


def evaluate_risk_predictions(
    labels: np.ndarray,
    probabilities: np.ndarray,
    *,
    target_fpr: float = 0.01,
) -> dict[str, Any]:
    labels = np.asarray(labels, dtype=int)
    probabilities = np.asarray(probabilities, dtype=float)
    predicted = probabilities.argmax(axis=1)
    attack_labels = (labels != 0).astype(int)
    attack_scores = 1.0 - probabilities[:, 0]
    threshold = threshold_at_fpr(attack_labels, attack_scores, target_fpr)
    report = classification_report(
        labels,
        predicted,
        labels=list(range(len(RISK_LABELS))),
        target_names=list(RISK_LABELS),
        output_dict=True,
        zero_division=0,
    )
    metrics: dict[str, Any] = {
        "accuracy": float(accuracy_score(labels, predicted)),
        "macro_f1": float(report["macro avg"]["f1-score"]),
        "classification_report": report,
        "ece": expected_calibration_error(probabilities, labels),
        "brier": multiclass_brier(probabilities, labels),
        "nll": float(log_loss(labels, probabilities, labels=list(range(len(RISK_LABELS))))),
        "operating_point": binary_operating_point(attack_labels, attack_scores, threshold),
    }
    if len(np.unique(attack_labels)) == 2:
        metrics["attack_auroc"] = float(roc_auc_score(attack_labels, attack_scores))
        metrics["attack_auprc"] = float(average_precision_score(attack_labels, attack_scores))
        metrics["attack_brier"] = float(brier_score_loss(attack_labels, attack_scores))
    return metrics
