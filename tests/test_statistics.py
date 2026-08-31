from __future__ import annotations

import numpy as np
import pytest

from intentfence.statistics import (
    bootstrap_percentile,
    holm_adjust,
    paired_bootstrap_difference,
    paired_effect_size,
    summarize_seed_metrics,
)
from scripts.summarize_seed_runs import summarize_runs


def test_bootstrap_percentile_is_deterministic_and_serializable() -> None:
    values = np.arange(8, dtype=float)
    kwargs = {
        "cluster_ids": ["a", "a", "b", "b", "c", "c", "d", "d"],
        "strata": [42, 42, 42, 42, 52, 52, 52, 52],
        "n_resamples": 64,
        "seed": 7,
    }
    first = bootstrap_percentile((values,), lambda sample: float(np.mean(sample)), **kwargs)
    second = bootstrap_percentile((values,), lambda sample: float(np.mean(sample)), **kwargs)

    assert first.as_dict() == second.as_dict()
    assert first.n_resamples == first.valid_resamples == 64
    assert first.method == "paired_cluster_percentile_with_seed_outer_stratum"
    assert first.lower <= first.estimate <= first.upper


def test_paired_bootstrap_uses_same_resampled_rows_for_both_variants() -> None:
    labels = np.array([0, 1, 0, 1])
    baseline = np.array([0.1, 0.2, 0.3, 0.4])
    candidate = baseline + 1.0

    summary = paired_bootstrap_difference(
        labels,
        baseline,
        candidate,
        lambda _labels, scores: float(np.mean(scores)),
        n_resamples=32,
        seed=11,
    )

    assert summary.estimate == pytest.approx(1.0)
    assert summary.lower == pytest.approx(1.0)
    assert summary.upper == pytest.approx(1.0)


def test_bootstrap_rejects_non_finite_statistic() -> None:
    with pytest.raises(ValueError, match="finite observed estimate"):
        bootstrap_percentile((np.ones(3),), lambda _sample: float("nan"), n_resamples=2)


def test_paired_effect_size_and_seed_summary_are_explicit() -> None:
    effect = paired_effect_size(np.array([1.0, 2.0, 3.0]))
    assert effect["n"] == 3
    assert effect["mean_difference"] == pytest.approx(2.0)
    assert effect["std_difference"] == pytest.approx(1.0)
    assert effect["cohens_dz"] == pytest.approx(2.0)

    constant_effect = paired_effect_size(np.array([0.0, 0.0]))
    assert constant_effect["cohens_dz"] is None

    summary = summarize_seed_metrics(
        {52: 0.4, 42: 0.6, 62: 0.8}, metric_name="risk_macro_f1"
    )
    assert summary["per_seed"] == {"42": 0.6, "52": 0.4, "62": 0.8}
    assert summary["mean"] == pytest.approx(0.6)
    assert summary["std"] == pytest.approx(0.2)
    assert summary["range"] == pytest.approx(0.4)


def test_holm_adjust_is_monotonic_and_preserves_names() -> None:
    adjusted = holm_adjust({"h3": 0.2, "h1": 0.01, "h2": 0.04})
    assert adjusted == {"h3": pytest.approx(0.2), "h1": pytest.approx(0.03), "h2": pytest.approx(0.08)}


def test_seed_summary_cli_payload_groups_variants_and_metrics() -> None:
    report = summarize_runs(
        {
            "protocol_version": "1.0.0",
            "runs": [
                {"variant": "B", "seed": 52, "metrics": {"f1": 0.5}},
                {"variant": "A", "seed": 42, "metrics": {"f1": 0.4}},
                {"variant": "B", "seed": 42, "metrics": {"f1": 0.7}},
            ],
        },
        source_sha256="a" * 64,
    )

    assert report["status"] == "summary_only"
    assert report["variants"]["B"]["f1"]["mean"] == pytest.approx(0.6)
    assert report["variants"]["A"]["f1"]["std"] is None
