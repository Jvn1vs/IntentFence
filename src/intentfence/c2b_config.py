from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

C2B_MODEL_NAME = "microsoft/deberta-v3-base"
C2B_MODEL_REVISION = "8ccc9b6f36199bec6961081d44eb72fb3f7353f3"
C2B_ALLOWED_SEEDS = (42, 52, 62)

C2B_VARIANTS: dict[str, tuple[str, float]] = {
    "deberta-v3-base-text-risk": ("text", 0.0),
    "deberta-v3-base-context-risk": ("context", 0.0),
    "deberta-v3-base-action-risk": ("action", 0.0),
    "deberta-v3-base-action-multitask": ("action", 0.5),
}

C2B_COMMON_VALUES: dict[str, Any] = {
    "model_name": C2B_MODEL_NAME,
    "model_revision": C2B_MODEL_REVISION,
    "max_length": 384,
    "train_batch_size": 8,
    "eval_batch_size": 16,
    "gradient_accumulation_steps": 2,
    "learning_rate": 2.0e-5,
    "weight_decay": 0.01,
    "epochs": 5,
    "warmup_ratio": 0.10,
    "max_grad_norm": 1.0,
    "mixed_precision": "fp16",
    "gradient_checkpointing": False,
    "early_stopping_patience": 2,
    "early_stopping": False,
    "alignment_target": "task_alignment",
}


def _read_config(path: Path) -> dict[str, Any]:
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise ValueError(f"C2b config is not valid UTF-8 YAML: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("C2b config must be a YAML mapping")
    return payload


def validate_c2b_config(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    payload = _read_config(source)
    errors: list[str] = []
    expected_keys = set(C2B_COMMON_VALUES) | {
        "run_name",
        "input_mode",
        "alignment_loss_weight",
        "seed",
    }
    missing = sorted(expected_keys - set(payload))
    extra = sorted(set(payload) - expected_keys)
    if missing:
        errors.append(f"missing fields: {missing}")
    if extra:
        errors.append(f"unexpected fields: {extra}")

    for field, expected in C2B_COMMON_VALUES.items():
        if payload.get(field) != expected:
            errors.append(f"{field} must equal {expected!r}")

    run_name = payload.get("run_name")
    variant = C2B_VARIANTS.get(run_name)
    if variant is None:
        errors.append(f"run_name must be one of {sorted(C2B_VARIANTS)}")
    else:
        input_mode, alignment_loss_weight = variant
        if payload.get("input_mode") != input_mode:
            errors.append(f"input_mode must equal {input_mode!r} for {run_name}")
        if payload.get("alignment_loss_weight") != alignment_loss_weight:
            errors.append(
                f"alignment_loss_weight must equal {alignment_loss_weight!r} for {run_name}"
            )

    seed = payload.get("seed")
    if isinstance(seed, bool) or seed not in C2B_ALLOWED_SEEDS:
        errors.append(f"seed must be one of the preregistered values {C2B_ALLOWED_SEEDS}")
    if errors:
        raise ValueError(f"C2b config validation failed for {source}: {'; '.join(errors)}")
    return payload
