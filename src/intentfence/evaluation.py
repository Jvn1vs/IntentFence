from __future__ import annotations

import json
import math
from collections import defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from statistics import NormalDist
from typing import Any

import numpy as np

from intentfence.constants import RISK_LABELS
from intentfence.metrics import binary_operating_point, evaluate_risk_predictions
from intentfence.run_manifest import sha256_file
from intentfence.statistics import bootstrap_percentile

PREDICTION_GROUP_FIELDS = ("scenario", "attack_family", "content_length_bucket")
TEST_SPLITS = frozenset({"test_a", "test_b", "test_c", "test_d"})


def content_length_bucket(length: int) -> str:
    """Map character length to fixed, descriptive analysis buckets."""

    if isinstance(length, bool) or not isinstance(length, (int, np.integer)) or length < 0:
        raise ValueError("content length must be a non-negative integer")
    length = int(length)
    if length < 128:
        return "[0,128)"
    if length < 512:
        return "[128,512)"
    if length < 2048:
        return "[512,2048)"
    return "[2048,+)"


def validate_prediction_rows(
    rows: Sequence[Mapping[str, Any]], *, expected_split: str | None = None
) -> list[dict[str, Any]]:
    """Validate JSONL predictions before any metric or error-analysis calculation."""

    if not rows:
        raise ValueError("prediction file is empty")
    validated: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    identities: set[tuple[str, str]] = set()
    splits: set[str] = set()
    expected_probability_keys = set(RISK_LABELS)
    for index, source_row in enumerate(rows, start=1):
        row = dict(source_row)
        sample_id = row.get("sample_id")
        if not isinstance(sample_id, str) or not sample_id.strip():
            raise ValueError(f"row {index}: sample_id must be a non-empty string")
        if sample_id in seen_ids:
            raise ValueError(f"row {index}: duplicate sample_id={sample_id}")
        seen_ids.add(sample_id)

        split = row.get("split")
        if not isinstance(split, str) or not split.strip():
            raise ValueError(f"row {index}: split must be explicit")
        if expected_split is not None and split != expected_split:
            raise ValueError(
                f"row {index}: split={split!r} does not match expected {expected_split!r}"
            )
        splits.add(split)

        true_risk = row.get("true_risk")
        predicted_risk = row.get("predicted_risk")
        if true_risk not in RISK_LABELS or predicted_risk not in RISK_LABELS:
            raise ValueError(f"row {index}: true_risk and predicted_risk must use the frozen labels")
        probabilities = row.get("risk_probabilities")
        if not isinstance(probabilities, Mapping) or set(probabilities) != expected_probability_keys:
            raise ValueError(f"row {index}: risk_probabilities keys do not match the frozen labels")
        normalized_probabilities: dict[str, float] = {}
        for label in RISK_LABELS:
            try:
                value = float(probabilities[label])
            except (TypeError, ValueError) as exc:
                raise ValueError(f"row {index}: invalid probability for {label}") from exc
            if not np.isfinite(value) or not 0 <= value <= 1:
                raise ValueError(f"row {index}: probability for {label} must be finite in [0, 1]")
            normalized_probabilities[label] = value
        if not np.isclose(sum(normalized_probabilities.values()), 1.0, atol=1e-8, rtol=1e-8):
            raise ValueError(f"row {index}: risk probabilities must sum to 1")

        try:
            attack_score = float(row.get("attack_score"))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"row {index}: attack_score must be numeric") from exc
        if not np.isfinite(attack_score) or not 0 <= attack_score <= 1:
            raise ValueError(f"row {index}: attack_score must be finite in [0, 1]")
        if not np.isclose(
            attack_score, 1.0 - normalized_probabilities["benign"], atol=1e-8, rtol=1e-8
        ):
            raise ValueError(f"row {index}: attack_score is inconsistent with benign probability")
        expected_prediction = max(normalized_probabilities, key=normalized_probabilities.get)
        if predicted_risk != expected_prediction:
            raise ValueError(f"row {index}: predicted_risk is inconsistent with probabilities")

        template_group = row.get("template_group")
        if not isinstance(template_group, str) or not template_group.strip():
            raise ValueError(f"row {index}: template_group is required for cluster bootstrap")
        backend = str(row.get("backend", "unknown"))
        revision = str(row.get("revision", "unknown"))
        identities.add((backend, revision))

        raw_length = row.get("content_length")
        if raw_length is not None:
            if isinstance(raw_length, bool) or not isinstance(raw_length, (int, np.integer)):
                raise ValueError(f"row {index}: content_length must be an integer")
            row["content_length"] = int(raw_length)
            derived_bucket = content_length_bucket(int(raw_length))
            if row.get("content_length_bucket", derived_bucket) != derived_bucket:
                raise ValueError(f"row {index}: content_length_bucket does not match content_length")
            row["content_length_bucket"] = derived_bucket
        else:
            row["content_length_bucket"] = str(row.get("content_length_bucket", "unknown"))

        row.update(
            {
                "sample_id": sample_id,
                "split": split,
                "true_risk": true_risk,
                "predicted_risk": predicted_risk,
                "risk_probabilities": normalized_probabilities,
                "attack_score": attack_score,
                "template_group": template_group,
                "scenario": str(row.get("scenario", "unknown")),
                "attack_family": str(row.get("attack_family", "none")),
            }
        )
        validated.append(row)
    if len(splits) != 1:
        raise ValueError(f"prediction file mixes split values: {sorted(splits)}")
    if len(identities) != 1:
        raise ValueError(f"prediction identity is not unique: {sorted(identities)}")
    return validated


def load_prediction_jsonl(path: str | Path, *, expected_split: str | None = None) -> list[dict[str, Any]]:
    source_path = Path(path)
    rows: list[dict[str, Any]] = []
    try:
        with source_path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"invalid JSON at {source_path}:{line_number}") from exc
                if not isinstance(payload, dict):
                    raise ValueError(f"row {line_number}: prediction must be a JSON object")
                rows.append(payload)
    except OSError as exc:
        raise FileNotFoundError(f"cannot read prediction file: {source_path}") from exc
    return validate_prediction_rows(rows, expected_split=expected_split)


def _arrays(rows: Sequence[Mapping[str, Any]]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    labels = np.asarray([RISK_LABELS.index(row["true_risk"]) for row in rows], dtype=int)
    probabilities = np.asarray(
        [[row["risk_probabilities"][label] for label in RISK_LABELS] for row in rows],
        dtype=float,
    )
    scores = np.asarray([row["attack_score"] for row in rows], dtype=float)
    return labels, probabilities, scores


def wilson_interval(
    successes: int, trials: int, *, confidence_level: float = 0.95
) -> dict[str, float | int]:
    """Return an exact-count Wilson interval for a binomial proportion."""

    if isinstance(successes, bool) or isinstance(trials, bool) or successes < 0 or trials <= 0:
        raise ValueError("successes must be non-negative and trials must be positive")
    if successes > trials:
        raise ValueError("successes cannot exceed trials")
    if not 0 < confidence_level < 1:
        raise ValueError("confidence_level must be in (0, 1)")
    z = NormalDist().inv_cdf(0.5 + confidence_level / 2)
    proportion = successes / trials
    denominator = 1 + z**2 / trials
    center = (proportion + z**2 / (2 * trials)) / denominator
    half_width = z * math.sqrt(
        proportion * (1 - proportion) / trials + z**2 / (4 * trials**2)
    ) / denominator
    return {
        "successes": int(successes),
        "trials": int(trials),
        "estimate": float(proportion),
        "lower": float(max(0.0, center - half_width)),
        "upper": float(min(1.0, center + half_width)),
        "confidence_level": float(confidence_level),
        "method": "wilson",
    }


def _bootstrap_operating_point(
    rows: Sequence[Mapping[str, Any]],
    *,
    threshold: float,
    metric: str,
    n_resamples: int,
    confidence_level: float,
    seed: int,
) -> dict[str, Any]:
    labels, _, scores = _arrays(rows)
    attack_labels = (labels != 0).astype(int)

    def statistic(resampled_labels: np.ndarray, resampled_scores: np.ndarray) -> float:
        point = binary_operating_point(resampled_labels, resampled_scores, threshold)
        return float(point[metric])

    return bootstrap_percentile(
        (attack_labels, scores),
        statistic,
        cluster_ids=[row["template_group"] for row in rows],
        n_resamples=n_resamples,
        confidence_level=confidence_level,
        seed=seed,
        method="cluster_percentile_fixed_calibration_threshold",
    ).as_dict()


def summarize_prediction_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    attack_threshold: float,
    target_fpr: float = 0.01,
    bootstrap_resamples: int = 10_000,
    confidence_level: float = 0.95,
    bootstrap_seed: int = 42,
) -> dict[str, Any]:
    validated = validate_prediction_rows(rows)
    if not np.isfinite(attack_threshold) or not 0 <= attack_threshold <= 1:
        raise ValueError("attack_threshold must be a finite value in [0, 1]")
    if not 0 <= target_fpr < 1:
        raise ValueError("target_fpr must be in [0, 1)")
    if bootstrap_resamples <= 0:
        raise ValueError("bootstrap_resamples must be positive")
    if not 0 < confidence_level < 1:
        raise ValueError("confidence_level must be in (0, 1)")
    labels, probabilities, _ = _arrays(validated)
    metrics = evaluate_risk_predictions(
        labels,
        probabilities,
        target_fpr=target_fpr,
        attack_threshold=attack_threshold,
    )
    operating_point = metrics["operating_point"]
    benign_count = int(np.sum(labels == 0))
    false_positive_count = int(operating_point["fp"])
    result: dict[str, Any] = {
        "split": validated[0]["split"],
        "sample_count": len(validated),
        "attack_threshold": float(attack_threshold),
        "threshold_source": "calibration_only",
        "metrics": metrics,
        "confidence_intervals": {
            "fpr": _bootstrap_operating_point(
                validated,
                threshold=attack_threshold,
                metric="fpr",
                n_resamples=bootstrap_resamples,
                confidence_level=confidence_level,
                seed=bootstrap_seed,
            ),
            "tpr": _bootstrap_operating_point(
                validated,
                threshold=attack_threshold,
                metric="tpr",
                n_resamples=bootstrap_resamples,
                confidence_level=confidence_level,
                seed=bootstrap_seed + 1,
            ),
        },
        "benign_fpr_wilson": (
            wilson_interval(false_positive_count, benign_count, confidence_level=confidence_level)
            if benign_count
            else {"status": "insufficient_benign_support"}
        ),
    }
    return result


def grouped_prediction_summaries(
    rows: Sequence[Mapping[str, Any]],
    *,
    attack_threshold: float,
    bootstrap_resamples: int = 10_000,
    confidence_level: float = 0.95,
    bootstrap_seed: int = 42,
) -> dict[str, dict[str, dict[str, Any]]]:
    validated = validate_prediction_rows(rows)
    grouped: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    for row in validated:
        for field in PREDICTION_GROUP_FIELDS:
            grouped[field][str(row.get(field, "unknown"))].append(row)
    return {
        field: {
            value: summarize_prediction_rows(
                group_rows,
                attack_threshold=attack_threshold,
                bootstrap_resamples=bootstrap_resamples,
                confidence_level=confidence_level,
                bootstrap_seed=bootstrap_seed,
            )
            for value, group_rows in sorted(values.items())
        }
        for field, values in grouped.items()
    }


def _compact_error(row: Mapping[str, Any]) -> dict[str, Any]:
    probabilities = row["risk_probabilities"]
    return {
        "sample_id": row["sample_id"],
        "split": row["split"],
        "template_group": row["template_group"],
        "scenario": row.get("scenario", "unknown"),
        "attack_family": row.get("attack_family", "none"),
        "true_risk": row["true_risk"],
        "predicted_risk": row["predicted_risk"],
        "attack_score": row["attack_score"],
        "confidence": max(probabilities.values()),
    }


def error_analysis(rows: Sequence[Mapping[str, Any]], *, max_items: int = 25) -> dict[str, Any]:
    validated = validate_prediction_rows(rows)
    if max_items <= 0:
        raise ValueError("max_items must be positive")
    false_negatives = [
        row for row in validated if row["true_risk"] != "benign" and row["predicted_risk"] == "benign"
    ]
    false_positives = [
        row for row in validated if row["true_risk"] == "benign" and row["predicted_risk"] != "benign"
    ]
    misclassified = [row for row in validated if row["true_risk"] != row["predicted_risk"]]
    return {
        "false_negatives": [
            _compact_error(row)
            for row in sorted(false_negatives, key=lambda item: (item["attack_score"], item["sample_id"]))[
                :max_items
            ]
        ],
        "false_positives": [
            _compact_error(row)
            for row in sorted(
                false_positives, key=lambda item: (-item["attack_score"], item["sample_id"])
            )[:max_items]
        ],
        "high_confidence_misclassifications": [
            _compact_error(row)
            for row in sorted(
                misclassified,
                key=lambda item: (-max(item["risk_probabilities"].values()), item["sample_id"]),
            )[:max_items]
        ],
        "counts": {
            "false_negatives": len(false_negatives),
            "false_positives": len(false_positives),
            "misclassified": len(misclassified),
        },
    }


def compare_prediction_rows(
    baseline_rows: Sequence[Mapping[str, Any]],
    candidate_rows: Sequence[Mapping[str, Any]],
    *,
    baseline_threshold: float,
    candidate_threshold: float,
    endpoint: str,
    n_resamples: int = 10_000,
    confidence_level: float = 0.95,
    bootstrap_seed: int = 42,
) -> dict[str, Any]:
    """Compare paired prediction files at their separately frozen thresholds."""

    if endpoint not in {"fpr", "tpr"}:
        raise ValueError("endpoint must be 'fpr' or 'tpr'")
    baseline = validate_prediction_rows(baseline_rows)
    candidate = validate_prediction_rows(candidate_rows)
    baseline_by_id = {row["sample_id"]: row for row in baseline}
    candidate_by_id = {row["sample_id"]: row for row in candidate}
    if set(baseline_by_id) != set(candidate_by_id):
        raise ValueError("paired prediction files must contain exactly the same sample IDs")
    ordered_ids = sorted(baseline_by_id)
    pair_fields = ("true_risk", "template_group", "scenario", "attack_family", "content_length_bucket")
    for sample_id in ordered_ids:
        left = baseline_by_id[sample_id]
        right = candidate_by_id[sample_id]
        if any(left[field] != right[field] for field in pair_fields):
            raise ValueError(f"paired metadata differs for sample_id={sample_id}")

    baseline_ordered = [baseline_by_id[sample_id] for sample_id in ordered_ids]
    candidate_ordered = [candidate_by_id[sample_id] for sample_id in ordered_ids]
    labels, _, baseline_scores = _arrays(baseline_ordered)
    _, _, candidate_scores = _arrays(candidate_ordered)
    attack_labels = (labels != 0).astype(int)
    if endpoint == "fpr" and not np.any(attack_labels == 0):
        raise ValueError("FPR comparison requires benign samples")
    if endpoint == "tpr" and not np.any(attack_labels == 1):
        raise ValueError("TPR comparison requires attack samples")
    if not np.isfinite(baseline_threshold) or not 0 <= baseline_threshold <= 1:
        raise ValueError("baseline_threshold must be a finite value in [0, 1]")
    if not np.isfinite(candidate_threshold) or not 0 <= candidate_threshold <= 1:
        raise ValueError("candidate_threshold must be a finite value in [0, 1]")

    def endpoint_statistic(labels_array: np.ndarray, scores: np.ndarray, threshold: float) -> float:
        point = binary_operating_point(labels_array, scores, threshold)
        return float(point[endpoint])

    difference = bootstrap_percentile(
        (attack_labels, baseline_scores, candidate_scores),
        lambda labels_array, baseline_array, candidate_array: endpoint_statistic(
            labels_array, candidate_array, candidate_threshold
        )
        - endpoint_statistic(labels_array, baseline_array, baseline_threshold),
        cluster_ids=[row["template_group"] for row in baseline_ordered],
        n_resamples=n_resamples,
        confidence_level=confidence_level,
        seed=bootstrap_seed,
        method="paired_cluster_percentile_fixed_variant_thresholds",
    ).as_dict()
    return {
        "endpoint": endpoint,
        "split": baseline_ordered[0]["split"],
        "paired_samples": len(ordered_ids),
        "baseline_threshold": float(baseline_threshold),
        "candidate_threshold": float(candidate_threshold),
        "baseline": binary_operating_point(
            attack_labels, baseline_scores, baseline_threshold
        ),
        "candidate": binary_operating_point(
            attack_labels, candidate_scores, candidate_threshold
        ),
        "difference_candidate_minus_baseline": difference,
    }


def build_prediction_report(
    rows: Sequence[Mapping[str, Any]],
    *,
    attack_threshold: float,
    max_error_items: int = 25,
    bootstrap_resamples: int = 10_000,
    confidence_level: float = 0.95,
    bootstrap_seed: int = 42,
) -> dict[str, Any]:
    validated = validate_prediction_rows(rows)
    summary = summarize_prediction_rows(
        validated,
        attack_threshold=attack_threshold,
        bootstrap_resamples=bootstrap_resamples,
        confidence_level=confidence_level,
        bootstrap_seed=bootstrap_seed,
    )
    identity = {
        "backend": str(validated[0].get("backend", "unknown")),
        "revision": str(validated[0].get("revision", "unknown")),
        "split": validated[0]["split"],
    }
    return {
        "schema_version": 1,
        "status": "analysis_only",
        "claim_scope": "supplied_predictions_only_no_new_model_or_final_test_access",
        "identity": identity,
        "overall": summary,
        "groups": grouped_prediction_summaries(
            validated,
            attack_threshold=attack_threshold,
            bootstrap_resamples=bootstrap_resamples,
            confidence_level=confidence_level,
            bootstrap_seed=bootstrap_seed,
        ),
        "error_analysis": error_analysis(validated, max_items=max_error_items),
        "limitations": [
            "Confidence intervals use template_group cluster bootstrap at a supplied frozen threshold.",
            "Cross-seed aggregate intervals require explicit per-seed paired inputs and are not inferred here.",
            "Error analysis lists identifiers and metadata, not raw untrusted content.",
        ],
    }


def prediction_file_provenance(path: str | Path) -> dict[str, str]:
    source_path = Path(path)
    return {"path": str(source_path.resolve()), "sha256": sha256_file(source_path)}
