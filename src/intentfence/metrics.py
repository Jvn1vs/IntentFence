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
    if logits.ndim != 2 or logits.shape[0] == 0 or logits.shape[1] == 0:
        raise ValueError("logits must be a non-empty [samples, classes] array")
    if not np.isfinite(logits).all():
        raise ValueError("logits must contain only finite values")
    shifted = logits - np.max(logits, axis=1, keepdims=True)
    exponentials = np.exp(shifted)
    return exponentials / exponentials.sum(axis=1, keepdims=True)


def _validate_probabilities_and_labels(
    probabilities: np.ndarray, labels: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    probabilities_array = np.asarray(probabilities, dtype=float)
    labels_array = np.asarray(labels)
    if (
        probabilities_array.ndim != 2
        or probabilities_array.shape[0] == 0
        or probabilities_array.shape[1] == 0
    ):
        raise ValueError("probabilities must be a non-empty [samples, classes] array")
    if labels_array.ndim != 1 or labels_array.shape[0] != probabilities_array.shape[0]:
        raise ValueError("labels must be a one-dimensional array matching probabilities")
    if not np.isfinite(probabilities_array).all():
        raise ValueError("probabilities must contain only finite values")
    if np.any(probabilities_array < 0.0) or np.any(probabilities_array > 1.0):
        raise ValueError("probabilities must lie in [0, 1]")
    if not np.allclose(probabilities_array.sum(axis=1), 1.0, rtol=1e-8, atol=1e-8):
        raise ValueError("each probability row must sum to 1")
    try:
        numeric_labels = np.asarray(labels_array, dtype=float)
    except (TypeError, ValueError) as exc:
        raise ValueError("labels must contain integer class ids") from exc
    if not np.isfinite(numeric_labels).all() or not np.equal(numeric_labels, np.floor(numeric_labels)).all():
        raise ValueError("labels must contain integer class ids")
    integer_labels = numeric_labels.astype(int)
    if np.any(integer_labels < 0) or np.any(integer_labels >= probabilities_array.shape[1]):
        raise ValueError("labels contain a class id outside the probability columns")
    return probabilities_array, integer_labels


def reliability_diagram(
    probabilities: np.ndarray, labels: np.ndarray, n_bins: int = 15
) -> list[dict[str, float | int | None]]:
    """Return JSON-ready confidence/accuracy points for a reliability diagram."""

    if not isinstance(n_bins, int) or isinstance(n_bins, bool) or n_bins <= 0:
        raise ValueError("n_bins must be a positive integer")
    probabilities, labels = _validate_probabilities_and_labels(probabilities, labels)
    confidences = probabilities.max(axis=1)
    predictions = probabilities.argmax(axis=1)
    correctness = predictions == labels
    boundaries = np.linspace(0.0, 1.0, n_bins + 1)
    diagram: list[dict[str, float | int | None]] = []
    for index, (lower, upper) in enumerate(
        zip(boundaries[:-1], boundaries[1:], strict=True)
    ):
        mask = (
            (confidences >= lower) & (confidences <= upper)
            if index == 0
            else (confidences > lower) & (confidences <= upper)
        )
        count = int(mask.sum())
        mean_confidence = float(np.mean(confidences[mask])) if count else None
        accuracy = float(np.mean(correctness[mask])) if count else None
        gap = abs(accuracy - mean_confidence) if count else None
        diagram.append(
            {
                "bin_index": index,
                "lower": float(lower),
                "upper": float(upper),
                "count": count,
                "fraction": float(count / len(confidences)),
                "mean_confidence": mean_confidence,
                "accuracy": accuracy,
                "gap": gap,
            }
        )
    return diagram


def expected_calibration_error(
    probabilities: np.ndarray, labels: np.ndarray, n_bins: int = 15
) -> float:
    diagram = reliability_diagram(probabilities, labels, n_bins=n_bins)
    return float(
        sum(
            float(point["fraction"]) * float(point["gap"])
            for point in diagram
            if point["count"] and point["gap"] is not None
        )
    )


def classwise_ece(
    probabilities: np.ndarray,
    labels: np.ndarray,
    *,
    n_bins: int = 15,
    min_class_samples: int = 10,
) -> dict[str, dict[str, Any]]:
    """Report one-vs-rest ECE and explicitly mark insufficient class support."""

    if (
        not isinstance(min_class_samples, int)
        or isinstance(min_class_samples, bool)
        or min_class_samples <= 0
    ):
        raise ValueError("min_class_samples must be a positive integer")
    probabilities, labels = _validate_probabilities_and_labels(probabilities, labels)
    result: dict[str, dict[str, Any]] = {}
    for class_index in range(probabilities.shape[1]):
        positive = labels == class_index
        positive_count = int(positive.sum())
        negative_count = int((~positive).sum())
        sufficient = (
            positive_count >= min_class_samples and negative_count >= min_class_samples
        )
        entry: dict[str, Any] = {
            "class_index": class_index,
            "positive_count": positive_count,
            "negative_count": negative_count,
            "min_class_samples": min_class_samples,
            "sufficient": sufficient,
            "status": "ok" if sufficient else "insufficient_class_support",
            "ece": None,
        }
        if sufficient:
            binary_probabilities = np.column_stack(
                (1.0 - probabilities[:, class_index], probabilities[:, class_index])
            )
            entry["ece"] = expected_calibration_error(
                binary_probabilities,
                positive.astype(int),
                n_bins=n_bins,
            )
        result[str(class_index)] = entry
    return result


def calibration_metrics(
    probabilities: np.ndarray,
    labels: np.ndarray,
    *,
    n_bins: int = 15,
    min_class_samples: int = 10,
) -> dict[str, Any]:
    """Calculate calibration metrics and their audit-friendly supporting data."""

    probabilities, labels = _validate_probabilities_and_labels(probabilities, labels)
    return {
        "n_samples": int(len(labels)),
        "ece": expected_calibration_error(probabilities, labels, n_bins=n_bins),
        "brier": multiclass_brier(probabilities, labels),
        "nll": float(log_loss(labels, probabilities, labels=list(range(probabilities.shape[1])))),
        "reliability_diagram": reliability_diagram(probabilities, labels, n_bins=n_bins),
        "classwise_ece": classwise_ece(
            probabilities,
            labels,
            n_bins=n_bins,
            min_class_samples=min_class_samples,
        ),
    }


def multiclass_brier(probabilities: np.ndarray, labels: np.ndarray) -> float:
    probabilities, labels = _validate_probabilities_and_labels(probabilities, labels)
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
