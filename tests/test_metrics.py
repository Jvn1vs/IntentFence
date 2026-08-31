from __future__ import annotations

import warnings

import numpy as np

from intentfence.calibration import TemperatureScaler
from intentfence.metrics import (
    binary_operating_point,
    calibration_metrics,
    classwise_ece,
    evaluate_risk_predictions,
    reliability_diagram,
    softmax,
    threshold_at_fpr,
)


def test_float32_softmax_is_normalized_without_sklearn_probability_warning():
    logits = np.array(
        [
            [2.1, -0.3, 0.4, 1.2, -1.0],
            [-1.2, 0.8, 1.1, -0.4, 0.2],
            [0.1, 0.2, 0.3, 0.4, 0.5],
            [1.7, -0.9, 0.0, 0.8, -0.2],
            [-0.2, 1.4, -0.7, 0.6, 0.3],
        ],
        dtype=np.float32,
    )
    probabilities = softmax(logits)

    assert probabilities.dtype == np.float64
    np.testing.assert_allclose(probabilities.sum(axis=1), 1.0, rtol=0.0, atol=1e-15)
    with warnings.catch_warnings():
        warnings.simplefilter("error", UserWarning)
        metrics = evaluate_risk_predictions(np.arange(5), probabilities)
    assert np.isfinite(metrics["nll"])


def test_threshold_respects_empirical_fpr():
    labels = np.array([0] * 100 + [1] * 10)
    scores = np.array(list(np.linspace(0, 0.5, 100)) + [0.8] * 10)
    threshold = threshold_at_fpr(labels, scores, 0.01)
    point = binary_operating_point(labels, scores, threshold)
    assert point["fpr"] <= 0.01
    assert point["tpr"] == 1.0


def test_evaluation_can_use_a_calibration_derived_threshold_without_reselecting_it():
    labels = np.array([0, 0, 1, 1])
    probabilities = np.array(
        [
            [0.8, 0.2, 0.0, 0.0, 0.0],
            [0.4, 0.6, 0.0, 0.0, 0.0],
            [0.7, 0.3, 0.0, 0.0, 0.0],
            [0.1, 0.9, 0.0, 0.0, 0.0],
        ]
    )

    metrics = evaluate_risk_predictions(labels, probabilities, attack_threshold=0.5)

    assert metrics["threshold_source"] == "calibration_only"
    assert metrics["operating_point"]["threshold"] == 0.5
    assert metrics["operating_point"]["fpr"] == 0.5


def test_temperature_is_positive_and_softens_overconfidence():
    logits = np.array([[8.0, 0.0], [8.0, 0.0], [8.0, 0.0], [8.0, 0.0]])
    labels = np.array([0, 0, 1, 1])
    scaler = TemperatureScaler().fit(logits, labels)
    assert scaler.temperature > 1.0
    assert scaler.predict_proba(logits)[0, 0] < softmax(logits)[0, 0]


def test_reliability_diagram_has_complete_bins_and_json_ready_values():
    probabilities = np.array(
        [
            [0.9, 0.1],
            [0.8, 0.2],
            [0.4, 0.6],
            [0.3, 0.7],
        ]
    )
    diagram = reliability_diagram(probabilities, np.array([0, 1, 0, 1]), n_bins=2)

    assert len(diagram) == 2
    assert sum(point["count"] for point in diagram) == 4
    assert all(set(point) == {
        "bin_index",
        "lower",
        "upper",
        "count",
        "fraction",
        "mean_confidence",
        "accuracy",
        "gap",
    } for point in diagram)


def test_classwise_ece_marks_insufficient_support_and_calibration_metrics_include_details():
    probabilities = np.array(
        [
            [0.9, 0.1, 0.0],
            [0.8, 0.2, 0.0],
            [0.1, 0.8, 0.1],
            [0.1, 0.7, 0.2],
            [0.1, 0.2, 0.7],
        ]
    )
    labels = np.array([0, 0, 1, 1, 2])

    classwise = classwise_ece(probabilities, labels, n_bins=3, min_class_samples=2)
    metrics = calibration_metrics(probabilities, labels, n_bins=3, min_class_samples=2)

    assert classwise["0"]["sufficient"] is True
    assert classwise["1"]["sufficient"] is True
    assert classwise["2"]["status"] == "insufficient_class_support"
    assert classwise["2"]["ece"] is None
    assert len(metrics["reliability_diagram"]) == 3
    assert set(metrics) == {
        "n_samples",
        "ece",
        "brier",
        "nll",
        "reliability_diagram",
        "classwise_ece",
    }
