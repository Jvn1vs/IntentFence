from __future__ import annotations

import warnings

import numpy as np

from intentfence.calibration import TemperatureScaler
from intentfence.metrics import (
    binary_operating_point,
    evaluate_risk_predictions,
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


def test_temperature_is_positive_and_softens_overconfidence():
    logits = np.array([[8.0, 0.0], [8.0, 0.0], [8.0, 0.0], [8.0, 0.0]])
    labels = np.array([0, 0, 1, 1])
    scaler = TemperatureScaler().fit(logits, labels)
    assert scaler.temperature > 1.0
    assert scaler.predict_proba(logits)[0, 0] < softmax(logits)[0, 0]
