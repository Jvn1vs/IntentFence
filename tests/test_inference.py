from __future__ import annotations

import numpy as np
import pytest

from intentfence.inference import _alignment_conflict_probability


def test_legacy_alignment_conflict_probability_uses_conflict_class() -> None:
    probabilities = np.asarray([0.35, 0.65], dtype=np.float64)

    assert _alignment_conflict_probability(
        probabilities, ("aligned", "conflict")
    ) == pytest.approx(0.65)


def test_task_alignment_conflict_probability_is_one_minus_aligned() -> None:
    probabilities = np.asarray([0.4, 0.2, 0.1, 0.3], dtype=np.float64)

    assert _alignment_conflict_probability(
        probabilities, ("aligned", "unrelated", "ambiguous", "malicious")
    ) == pytest.approx(0.6)
