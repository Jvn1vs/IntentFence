from __future__ import annotations

import numpy as np

from intentfence.calibration import TemperatureScaler
from intentfence.metrics import binary_operating_point, softmax, threshold_at_fpr


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
