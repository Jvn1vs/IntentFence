from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

Statistic = Callable[..., float]
PairedStatistic = Callable[[np.ndarray, np.ndarray], float]


@dataclass(frozen=True)
class BootstrapSummary:
    """A percentile interval with the inputs needed to reproduce it."""

    estimate: float
    lower: float
    upper: float
    confidence_level: float
    n_resamples: int
    valid_resamples: int
    seed: int
    method: str = "paired_cluster_percentile_with_seed_outer_stratum"

    def as_dict(self) -> dict[str, Any]:
        return {
            "estimate": self.estimate,
            "lower": self.lower,
            "upper": self.upper,
            "confidence_level": self.confidence_level,
            "n_resamples": self.n_resamples,
            "valid_resamples": self.valid_resamples,
            "seed": self.seed,
            "method": self.method,
        }


def _validate_bootstrap_options(
    *, n_resamples: int, confidence_level: float, seed: int
) -> None:
    if n_resamples <= 0:
        raise ValueError("n_resamples must be positive")
    if not 0 < confidence_level < 1:
        raise ValueError("confidence_level must be in (0, 1)")
    if isinstance(seed, bool) or not isinstance(seed, (int, np.integer)):
        raise ValueError("seed must be an integer")


def _metadata_values(
    values: Iterable[Any] | None,
    *,
    name: str,
    length: int,
    default: str,
) -> np.ndarray:
    if values is None:
        return np.full(length, default, dtype=object)
    output = np.asarray(list(values), dtype=object)
    if output.ndim != 1 or len(output) != length:
        raise ValueError(f"{name} must contain exactly {length} values")
    if any(value is None or str(value) == "" for value in output):
        raise ValueError(f"{name} cannot contain empty values")
    return output


def _cluster_blocks(
    length: int,
    *,
    cluster_ids: Iterable[Any] | None,
    strata: Iterable[Any] | None,
) -> dict[str, tuple[np.ndarray, ...]]:
    clusters = _metadata_values(
        cluster_ids, name="cluster_ids", length=length, default="row"
    )
    if cluster_ids is None:
        clusters = np.asarray([f"row-{index}" for index in range(length)], dtype=object)
    stratum_values = _metadata_values(
        strata, name="strata", length=length, default="all"
    )
    grouped: dict[str, dict[str, list[int]]] = {}
    for index, (stratum, cluster) in enumerate(zip(stratum_values, clusters, strict=True)):
        stratum_key = str(stratum)
        cluster_key = str(cluster)
        grouped.setdefault(stratum_key, {}).setdefault(cluster_key, []).append(index)
    return {
        stratum: tuple(
            np.asarray(grouped[stratum][cluster], dtype=int)
            for cluster in sorted(grouped[stratum])
        )
        for stratum in sorted(grouped)
    }


def _bootstrap_indices(
    length: int,
    *,
    cluster_ids: Iterable[Any] | None,
    strata: Iterable[Any] | None,
    n_resamples: int,
    seed: int,
) -> Iterable[np.ndarray]:
    blocks = _cluster_blocks(length, cluster_ids=cluster_ids, strata=strata)
    if not blocks:
        raise ValueError("at least one observation is required")
    stratum_keys = tuple(blocks)
    rng = np.random.default_rng(seed)
    for _ in range(n_resamples):
        selected_strata = rng.integers(0, len(stratum_keys), size=len(stratum_keys))
        selected_indices: list[np.ndarray] = []
        for stratum_index in selected_strata:
            stratum_blocks = blocks[stratum_keys[int(stratum_index)]]
            selected_blocks = rng.integers(0, len(stratum_blocks), size=len(stratum_blocks))
            selected_indices.extend(stratum_blocks[int(block_index)] for block_index in selected_blocks)
        yield np.concatenate(selected_indices)


def bootstrap_percentile(
    arrays: Sequence[np.ndarray],
    statistic: Statistic,
    *,
    cluster_ids: Iterable[Any] | None = None,
    strata: Iterable[Any] | None = None,
    n_resamples: int = 10_000,
    confidence_level: float = 0.95,
    seed: int = 42,
    method: str = "paired_cluster_percentile_with_seed_outer_stratum",
) -> BootstrapSummary:
    """Compute a deterministic cluster/seed-stratified percentile interval.

    All arrays are resampled with the same indices, so passing baseline and candidate
    predictions together preserves paired comparisons.  Strata are sampled as an outer
    bootstrap layer; clusters are sampled with replacement inside each selected stratum.
    With no cluster IDs, each row is treated as its own cluster.
    """

    _validate_bootstrap_options(
        n_resamples=n_resamples, confidence_level=confidence_level, seed=seed
    )
    if not arrays:
        raise ValueError("at least one array is required")
    values = tuple(np.asarray(array) for array in arrays)
    length = values[0].shape[0] if values[0].ndim else 0
    if length <= 0:
        raise ValueError("arrays must contain at least one observation")
    if any(array.ndim == 0 or array.shape[0] != length for array in values):
        raise ValueError("all arrays must have the same non-zero first dimension")
    observed = float(statistic(*values))
    if not np.isfinite(observed):
        raise ValueError("statistic must return a finite observed estimate")

    bootstrap_values = np.empty(n_resamples, dtype=float)
    for index, sample_indices in enumerate(
        _bootstrap_indices(
            length,
            cluster_ids=cluster_ids,
            strata=strata,
            n_resamples=n_resamples,
            seed=int(seed),
        )
    ):
        value = float(statistic(*(array[sample_indices] for array in values)))
        if not np.isfinite(value):
            raise ValueError(f"statistic returned a non-finite bootstrap value at replicate {index}")
        bootstrap_values[index] = value

    alpha = (1 - confidence_level) / 2
    lower, upper = np.quantile(
        bootstrap_values, [alpha, 1 - alpha], method="linear"
    )
    return BootstrapSummary(
        estimate=observed,
        lower=float(lower),
        upper=float(upper),
        confidence_level=float(confidence_level),
        n_resamples=n_resamples,
        valid_resamples=n_resamples,
        seed=int(seed),
        method=method,
    )


def paired_bootstrap_difference(
    labels: np.ndarray,
    baseline: np.ndarray,
    candidate: np.ndarray,
    statistic: PairedStatistic,
    *,
    cluster_ids: Iterable[Any] | None = None,
    strata: Iterable[Any] | None = None,
    n_resamples: int = 10_000,
    confidence_level: float = 0.95,
    seed: int = 42,
) -> BootstrapSummary:
    """Return candidate-minus-baseline for a paired statistic."""

    def difference(
        resampled_labels: np.ndarray,
        resampled_baseline: np.ndarray,
        resampled_candidate: np.ndarray,
    ) -> float:
        return float(
            statistic(resampled_labels, resampled_candidate)
            - statistic(resampled_labels, resampled_baseline)
        )

    return bootstrap_percentile(
        (np.asarray(labels), np.asarray(baseline), np.asarray(candidate)),
        difference,
        cluster_ids=cluster_ids,
        strata=strata,
        n_resamples=n_resamples,
        confidence_level=confidence_level,
        seed=seed,
    )


def paired_effect_size(differences: np.ndarray) -> dict[str, float | int | None]:
    """Summarize paired differences and Cohen's dz without hiding zero variance."""

    values = np.asarray(differences, dtype=float).reshape(-1)
    if len(values) < 2:
        raise ValueError("at least two paired differences are required")
    if not np.all(np.isfinite(values)):
        raise ValueError("differences must be finite")
    mean = float(np.mean(values))
    standard_deviation = float(np.std(values, ddof=1))
    cohens_dz: float | None = (
        None if standard_deviation == 0 else mean / standard_deviation
    )
    return {
        "n": int(len(values)),
        "mean_difference": mean,
        "std_difference": standard_deviation,
        "cohens_dz": cohens_dz,
    }


def summarize_seed_metrics(
    seed_values: Mapping[int, float], *, metric_name: str
) -> dict[str, Any]:
    """Summarize one scalar metric across explicitly supplied training seeds."""

    if not metric_name.strip():
        raise ValueError("metric_name must be non-empty")
    if not seed_values:
        raise ValueError("at least one seed result is required")
    normalized: dict[int, float] = {}
    for seed, value in seed_values.items():
        if isinstance(seed, bool) or not isinstance(seed, (int, np.integer)):
            raise ValueError("seed keys must be integers")
        numeric_value = float(value)
        if not np.isfinite(numeric_value):
            raise ValueError(f"metric value for seed {seed} must be finite")
        normalized[int(seed)] = numeric_value
    ordered = dict(sorted(normalized.items()))
    values = np.asarray(list(ordered.values()), dtype=float)
    return {
        "metric": metric_name,
        "n_seeds": len(ordered),
        "per_seed": {str(seed): value for seed, value in ordered.items()},
        "mean": float(np.mean(values)),
        "std": float(np.std(values, ddof=1)) if len(values) >= 2 else None,
        "min": float(np.min(values)),
        "max": float(np.max(values)),
        "range": float(np.max(values) - np.min(values)),
    }


def holm_adjust(p_values: Mapping[str, float]) -> dict[str, float]:
    """Apply Holm's step-down correction within one result table."""

    if not p_values:
        raise ValueError("at least one p-value is required")
    validated: dict[str, float] = {}
    for name, value in p_values.items():
        numeric_value = float(value)
        if not 0 <= numeric_value <= 1:
            raise ValueError(f"p-value for {name} must be in [0, 1]")
        validated[str(name)] = numeric_value
    count = len(validated)
    adjusted: dict[str, float] = {}
    running_max = 0.0
    for rank, (name, value) in enumerate(
        sorted(validated.items(), key=lambda item: (item[1], item[0]))
    ):
        corrected = min(1.0, (count - rank) * value)
        running_max = max(running_max, corrected)
        adjusted[name] = running_max
    return {name: adjusted[name] for name in validated}
