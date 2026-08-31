from __future__ import annotations

import math
import random
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass

from intentfence.constants import ALIGNMENT_TARGETS, INPUT_MODES, RISK_LABELS, TASK_ALIGNMENT_LABELS
from intentfence.schema import IntentSample


@dataclass(frozen=True)
class TrainingDataSummary:
    """Deterministic, non-statistical summary produced before model loading."""

    train_count: int
    validation_count: int
    train_risk_counts: dict[str, int]
    validation_risk_counts: dict[str, int]
    train_alignment_counts: dict[str, int]
    validation_alignment_counts: dict[str, int]
    alignment_target: str

    def as_dict(self) -> dict[str, object]:
        return {
            "train_count": self.train_count,
            "validation_count": self.validation_count,
            "train_risk_counts": self.train_risk_counts,
            "validation_risk_counts": self.validation_risk_counts,
            "train_alignment_counts": self.train_alignment_counts,
            "validation_alignment_counts": self.validation_alignment_counts,
            "alignment_target": self.alignment_target,
        }


def calculate_optimizer_steps(
    sample_count: int,
    *,
    batch_size: int,
    gradient_accumulation_steps: int,
    epochs: int,
) -> int:
    """Calculate optimizer updates without importing a training framework."""

    values = {
        "sample_count": sample_count,
        "batch_size": batch_size,
        "gradient_accumulation_steps": gradient_accumulation_steps,
        "epochs": epochs,
    }
    invalid = {name: value for name, value in values.items() if value <= 0}
    if invalid:
        raise ValueError(f"optimizer-step inputs must be positive; observed {invalid}")
    batches_per_epoch = math.ceil(sample_count / batch_size)
    return math.ceil(batches_per_epoch / gradient_accumulation_steps) * epochs


def _counts(samples: Iterable[IntentSample], field: str) -> dict[str, int]:
    values = [getattr(sample, field) for sample in samples]
    return dict(sorted(Counter(str(value) for value in values).items()))


def validate_training_inputs(
    train_samples: list[IntentSample],
    validation_samples: list[IntentSample],
    *,
    input_mode: str,
    alignment_target: str = "legacy_binary",
) -> TrainingDataSummary:
    """Validate the safety and split contract before tokenizer/model loading.

    This is an engineering preflight, not a training-readiness or statistical
    sufficiency claim.  It deliberately requires binary attack coverage in
    both roles because FPR/TPR validation is undefined without benign and
    attack examples, while leaving five-class coverage to the research gate.
    """

    if input_mode not in INPUT_MODES:
        raise ValueError(f"Unknown input_mode {input_mode!r}; expected one of {INPUT_MODES}")
    if alignment_target not in ALIGNMENT_TARGETS:
        raise ValueError(
            f"Unknown alignment_target {alignment_target!r}; expected one of {ALIGNMENT_TARGETS}"
        )
    if not train_samples or not validation_samples:
        raise ValueError("train and validation inputs must both contain at least one sample")

    for role, samples in (("train", train_samples), ("validation", validation_samples)):
        for sample in samples:
            if sample.split is not None and sample.split != role:
                raise ValueError(
                    f"{sample.sample_id}: input supplied as {role} but its split is {sample.split}"
                )
            if input_mode == "action" and (
                sample.action_provenance == "missing" or not sample.proposed_action
            ):
                raise ValueError(
                    f"{sample.sample_id}: action input mode requires a non-empty proposed_action"
                )
            if alignment_target == "task_alignment" and sample.task_alignment_label is None:
                raise ValueError(
                    f"{sample.sample_id}: task_alignment target requires task_alignment_label"
                )

    summaries = {
        role: _counts(samples, "risk_label")
        for role, samples in (("train", train_samples), ("validation", validation_samples))
    }
    for role, risk_counts in summaries.items():
        if risk_counts.get("benign", 0) == 0 or sum(
            count for label, count in risk_counts.items() if label != "benign"
        ) == 0:
            raise ValueError(
                f"{role} must contain both benign and attack samples before training; "
                f"observed risk counts={risk_counts}"
            )

    alignment_field = (
        "task_alignment_label" if alignment_target == "task_alignment" else "alignment_label"
    )
    alignment_summaries = {
        role: _counts(samples, alignment_field)
        for role, samples in (("train", train_samples), ("validation", validation_samples))
    }
    if alignment_target == "task_alignment":
        expected = set(TASK_ALIGNMENT_LABELS)
        for role, alignment_counts in alignment_summaries.items():
            missing = sorted(expected - set(alignment_counts))
            if missing:
                raise ValueError(
                    f"{role} task_alignment target lacks labels: {missing}; "
                    f"observed counts={alignment_counts}"
                )

    return TrainingDataSummary(
        train_count=len(train_samples),
        validation_count=len(validation_samples),
        train_risk_counts=summaries["train"],
        validation_risk_counts=summaries["validation"],
        train_alignment_counts=alignment_summaries["train"],
        validation_alignment_counts=alignment_summaries["validation"],
        alignment_target=alignment_target,
    )


def deterministic_stratified_subset(
    samples: list[IntentSample],
    limit: int | None,
    *,
    seed: int,
) -> list[IntentSample]:
    """Return a reproducible subset while retaining benign and attack coverage."""

    if limit is None or limit >= len(samples):
        return list(samples)
    if limit <= 0:
        raise ValueError("sample limit must be positive")
    if limit < 2:
        raise ValueError("sample limit must retain at least benign and attack coverage")

    rng = random.Random(seed)
    groups: dict[str, list[int]] = {label: [] for label in RISK_LABELS}
    for index, sample in enumerate(samples):
        groups[sample.risk_label].append(index)
    attack_groups = [label for label in RISK_LABELS if label != "benign" and groups[label]]
    required_groups = ["benign", attack_groups[0]] if groups["benign"] and attack_groups else []
    if len(required_groups) < 2:
        raise ValueError("cannot create a stratified subset without benign and attack samples")

    selected: set[int] = set()
    for label in required_groups:
        selected.add(rng.choice(groups[label]))

    remaining = [index for index in range(len(samples)) if index not in selected]
    rng.shuffle(remaining)
    selected.update(remaining[: limit - len(selected)])
    return [samples[index] for index in sorted(selected)]
