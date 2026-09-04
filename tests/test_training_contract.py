from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path

import pytest

import intentfence.train as train_module
from intentfence.schema import IntentSample
from intentfence.train import TrainingConfig, prepare_training_samples
from intentfence.training_contract import (
    calculate_optimizer_steps,
    deterministic_stratified_subset,
    validate_training_inputs,
)


def _sample(
    index: int,
    risk: str,
    *,
    split: str,
    task_alignment_label: str | None = None,
) -> IntentSample:
    return IntentSample(
        sample_id=f"sample-{index}",
        source="fixture",
        user_goal="summarize the page",
        untrusted_content=f"content {index}",
        proposed_action="return_summary()",
        risk_label=risk,
        alignment_label=int(risk != "benign"),
        task_alignment_label=task_alignment_label,
        template_group=f"group-{index}",
        split=split,
        action_provenance="source_field",
    )


def _write_jsonl(path: Path, rows: list[IntentSample]) -> None:
    path.write_text(
        "".join(f"{row.model_dump_json()}\n" for row in rows), encoding="utf-8"
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


def test_task_alignment_target_requires_all_four_labels() -> None:
    labels = ("aligned", "unrelated", "ambiguous", "malicious")
    train = [
        _sample(
            index,
            "benign" if index == 0 else "instruction_hijacking",
            split="train",
            task_alignment_label=label,
        )
        for index, label in enumerate(labels)
    ]
    validation = [
        _sample(
            index + 10,
            "benign" if index == 0 else "instruction_hijacking",
            split="validation",
            task_alignment_label=label,
        )
        for index, label in enumerate(labels)
    ]
    summary = validate_training_inputs(
        train,
        validation,
        input_mode="action",
        alignment_target="task_alignment",
    )
    assert summary.alignment_target == "task_alignment"
    assert summary.train_alignment_counts == {label: 1 for label in sorted(labels)}

    with pytest.raises(ValueError, match="lacks labels"):
        validate_training_inputs(
            train[:-1],
            validation,
            input_mode="action",
            alignment_target="task_alignment",
        )


def test_stratified_subset_is_reproducible_and_keeps_binary_coverage() -> None:
    samples = [
        _sample(index, "benign" if index < 4 else "instruction_hijacking", split="train")
        for index in range(10)
    ]
    left = deterministic_stratified_subset(samples, 5, seed=42)
    right = deterministic_stratified_subset(samples, 5, seed=42)
    assert [sample.sample_id for sample in left] == [sample.sample_id for sample in right]
    assert {sample.risk_label for sample in left} == {"benign", "instruction_hijacking"}


def test_optimizer_step_calculation_matches_training_loop() -> None:
    assert calculate_optimizer_steps(
        200, batch_size=8, gradient_accumulation_steps=1, epochs=1
    ) == 25
    assert calculate_optimizer_steps(
        201, batch_size=8, gradient_accumulation_steps=2, epochs=3
    ) == 39
    with pytest.raises(ValueError, match="must be positive"):
        calculate_optimizer_steps(
            0, batch_size=8, gradient_accumulation_steps=1, epochs=1
        )


def test_training_log_writer_replaces_valid_json_atomically(tmp_path: Path) -> None:
    path = tmp_path / "training_log.json"
    first_epoch = [{"epoch": 1, "macro_f1": 0.5}]
    second_epoch = first_epoch + [{"epoch": 2, "macro_f1": 0.6}]

    train_module._write_json_atomically(path, first_epoch)
    assert json.loads(path.read_text(encoding="utf-8")) == first_epoch

    train_module._write_json_atomically(path, second_epoch)
    assert json.loads(path.read_text(encoding="utf-8")) == second_epoch
    assert not (tmp_path / ".training_log.json.tmp").exists()


def test_cpu_smoke_config_enforces_sample_and_step_contract(tmp_path: Path) -> None:
    config = TrainingConfig.from_yaml("configs/deberta_small_cpu_smoke.yaml")
    train_rows = [
        _sample(index, "benign" if index % 2 == 0 else "instruction_hijacking", split="train")
        for index in range(210)
    ]
    validation_rows = [
        _sample(
            index + 1_000,
            "benign" if index % 2 == 0 else "instruction_hijacking",
            split="validation",
        )
        for index in range(110)
    ]
    train_path, validation_path = tmp_path / "train.jsonl", tmp_path / "validation.jsonl"
    _write_jsonl(train_path, train_rows)
    _write_jsonl(validation_path, validation_rows)

    _, _, summary, optimizer_steps = prepare_training_samples(
        config, train_path, validation_path
    )

    assert summary.train_count == 200
    assert summary.validation_count == 100
    assert optimizer_steps == 25


def test_small_abc_configs_only_change_run_name_and_input_mode() -> None:
    configs = [
        TrainingConfig.from_yaml(path)
        for path in (
            "configs/deberta_small_text.yaml",
            "configs/deberta_small_context.yaml",
            "configs/deberta_small.yaml",
        )
    ]
    normalized = []
    for config in configs:
        payload = asdict(config)
        payload.pop("run_name")
        payload.pop("input_mode")
        normalized.append(payload)
    assert normalized[0] == normalized[1] == normalized[2]
    assert [config.input_mode for config in configs] == ["text", "context", "action"]


def test_candidate_6_risk_configs_only_change_run_name_and_input_mode() -> None:
    configs = [
        TrainingConfig.from_yaml(path)
        for path in (
            "configs/deberta_small_c6_text_risk.yaml",
            "configs/deberta_small_c6_context_risk.yaml",
            "configs/deberta_small_c6_action_risk.yaml",
        )
    ]
    normalized = []
    for config in configs:
        payload = asdict(config)
        payload.pop("run_name")
        payload.pop("input_mode")
        normalized.append(payload)
    assert normalized[0] == normalized[1] == normalized[2]
    assert all(config.alignment_target == "task_alignment" for config in configs)
    assert all(config.alignment_loss_weight == 0.0 for config in configs)


def test_candidate_6_multitask_only_enables_alignment_loss() -> None:
    risk_only = TrainingConfig.from_yaml("configs/deberta_small_c6_action_risk.yaml")
    multitask = TrainingConfig.from_yaml(
        "configs/deberta_small_c6_action_multitask.yaml"
    )
    risk_payload = asdict(risk_only)
    multitask_payload = asdict(multitask)
    for payload in (risk_payload, multitask_payload):
        payload.pop("run_name")
        payload.pop("alignment_loss_weight")
    assert risk_payload == multitask_payload
    assert multitask.alignment_loss_weight == 0.5


def test_base_abc_configs_share_hyperparameters_and_backbone() -> None:
    configs = [
        TrainingConfig.from_yaml(path)
        for path in (
            "configs/deberta_base_text_risk.yaml",
            "configs/deberta_base_context_risk.yaml",
            "configs/deberta_base_action_risk.yaml",
        )
    ]
    normalized = []
    for config in configs:
        payload = asdict(config)
        payload.pop("run_name")
        payload.pop("input_mode")
        normalized.append(payload)
    assert normalized[0] == normalized[1] == normalized[2]
    assert all(config.model_name == "microsoft/deberta-v3-base" for config in configs)
    assert [config.input_mode for config in configs] == ["text", "context", "action"]
    assert all(config.alignment_loss_weight == 0.0 for config in configs)


def test_base_action_multitask_only_changes_loss_weight_from_action_risk() -> None:
    risk = TrainingConfig.from_yaml("configs/deberta_base_action_risk.yaml")
    multitask = TrainingConfig.from_yaml("configs/deberta_base_action_multitask.yaml")
    risk_payload = asdict(risk)
    multitask_payload = asdict(multitask)
    for payload in (risk_payload, multitask_payload):
        payload.pop("run_name")
        payload.pop("alignment_loss_weight")
    assert risk_payload == multitask_payload
    assert multitask.alignment_loss_weight == 0.5


def test_training_config_requires_full_model_revision() -> None:
    with pytest.raises(ValueError, match="40-character Git SHA"):
        TrainingConfig(
            run_name="invalid",
            model_name="microsoft/deberta-v3-small",
            model_revision="main",
        )


def test_base_training_cli_requires_c2b_authorization(monkeypatch, capsys, tmp_path: Path) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "intentfence.train",
            "--config",
            "configs/deberta_base_action_risk.yaml",
            "--train",
            str(tmp_path / "train.jsonl"),
            "--validation",
            str(tmp_path / "validation.jsonl"),
            "--output-dir",
            str(tmp_path / "output"),
        ],
    )

    with pytest.raises(SystemExit, match="2"):
        train_module.main()

    assert "C2b authorization arguments" in capsys.readouterr().err
