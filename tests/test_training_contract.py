from __future__ import annotations

import pytest

from intentfence.schema import IntentSample
from intentfence.training_contract import (
    deterministic_stratified_subset,
    validate_training_inputs,
)


def _sample(index: int, risk: str, *, split: str) -> IntentSample:
    return IntentSample(
        sample_id=f"sample-{index}",
        source="fixture",
        user_goal="summarize the page",
        untrusted_content=f"content {index}",
        proposed_action="return_summary()",
        risk_label=risk,
        alignment_label=int(risk != "benign"),
        template_group=f"group-{index}",
        split=split,
        action_provenance="source_field",
    )


def test_training_preflight_requires_binary_coverage_and_action() -> None:
    train = [
        _sample(0, "benign", split="train"),
        _sample(1, "instruction_hijacking", split="train"),
    ]
    validation = [
        _sample(2, "benign", split="validation"),
        _sample(3, "instruction_hijacking", split="validation"),
    ]
    summary = validate_training_inputs(train, validation, input_mode="action")
    assert summary.train_risk_counts == {"benign": 1, "instruction_hijacking": 1}

    with pytest.raises(ValueError, match="both benign and attack"):
        validate_training_inputs(
            train,
            [_sample(4, "instruction_hijacking", split="validation")],
            input_mode="action",
        )

    missing_action = _sample(5, "benign", split="train").model_copy(
        update={
            "proposed_action": "",
            "action_provenance": "missing",
            "adapter_missing_action": True,
        }
    )
    with pytest.raises(ValueError, match="requires a non-empty proposed_action"):
        validate_training_inputs([missing_action, train[1]], validation, input_mode="action")


def test_training_preflight_rejects_role_mismatch() -> None:
    train = [
        _sample(0, "benign", split="validation"),
        _sample(1, "instruction_hijacking", split="train"),
    ]
    validation = [
        _sample(2, "benign", split="validation"),
        _sample(3, "instruction_hijacking", split="validation"),
    ]
    with pytest.raises(ValueError, match="supplied as train"):
        validate_training_inputs(train, validation, input_mode="context")


def test_stratified_subset_is_reproducible_and_keeps_binary_coverage() -> None:
    samples = [
        _sample(index, "benign" if index < 4 else "instruction_hijacking", split="train")
        for index in range(10)
    ]
    left = deterministic_stratified_subset(samples, 5, seed=42)
    right = deterministic_stratified_subset(samples, 5, seed=42)
    assert [sample.sample_id for sample in left] == [sample.sample_id for sample in right]
    assert {sample.risk_label for sample in left} == {"benign", "instruction_hijacking"}
