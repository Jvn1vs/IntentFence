from __future__ import annotations

import argparse
import json
import math
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from intentfence.constants import RISK_LABELS, RISK_TO_ID
from intentfence.metrics import evaluate_risk_predictions, softmax
from intentfence.modeling import ModelMetadata, create_multitask_model, save_multitask_model
from intentfence.schema import IntentSample, read_jsonl
from intentfence.text import build_model_text
from intentfence.training_contract import (
    TrainingDataSummary,
    deterministic_stratified_subset,
    validate_training_inputs,
)


def _require_training() -> tuple[Any, Any, Any, Any]:
    try:
        import torch
        from torch import nn
        from torch.utils.data import DataLoader, Dataset
        from transformers import AutoTokenizer, get_linear_schedule_with_warmup
    except ImportError as exc:
        raise RuntimeError("Install training dependencies with: python -m pip install -e '.[ml]'") from exc
    return torch, nn, (DataLoader, Dataset), (AutoTokenizer, get_linear_schedule_with_warmup)


@dataclass
class TrainingConfig:
    run_name: str
    model_name: str
    input_mode: str = "action"
    max_length: int = 384
    train_batch_size: int = 8
    eval_batch_size: int = 16
    gradient_accumulation_steps: int = 1
    learning_rate: float = 2e-5
    weight_decay: float = 0.01
    epochs: int = 3
    warmup_ratio: float = 0.1
    max_grad_norm: float = 1.0
    mixed_precision: str = "fp16"
    gradient_checkpointing: bool = False
    early_stopping_patience: int = 2
    alignment_loss_weight: float = 0.5
    seed: int = 42

    @classmethod
    def from_yaml(cls, path: str | Path) -> TrainingConfig:
        return cls(**yaml.safe_load(Path(path).read_text(encoding="utf-8")))


def set_seed(seed: int, torch: Any) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def load_training_samples(
    config: TrainingConfig,
    train_path: Path,
    validation_path: Path,
) -> tuple[list[IntentSample], list[IntentSample], TrainingDataSummary]:
    train_samples, validation_samples = read_jsonl(train_path), read_jsonl(validation_path)
    summary = validate_training_inputs(
        train_samples, validation_samples, input_mode=config.input_mode
    )
    return train_samples, validation_samples, summary


def train(
    config: TrainingConfig,
    train_path: Path,
    validation_path: Path,
    output_dir: Path,
    *,
    max_train_samples: int | None = None,
    max_validation_samples: int | None = None,
) -> None:
    train_samples, validation_samples, _ = load_training_samples(
        config, train_path, validation_path
    )
    train_samples = deterministic_stratified_subset(
        train_samples, max_train_samples, seed=config.seed
    )
    validation_samples = deterministic_stratified_subset(
        validation_samples, max_validation_samples, seed=config.seed + 1
    )
    torch, nn, loader_types, transformer_types = _require_training()
    DataLoader, Dataset = loader_types
    AutoTokenizer, get_linear_schedule_with_warmup = transformer_types
    set_seed(config.seed, torch)

    tokenizer = AutoTokenizer.from_pretrained(config.model_name)

    class EncodedDataset(Dataset):
        def __init__(self, samples: list[IntentSample]) -> None:
            self.samples = samples

        def __len__(self) -> int:
            return len(self.samples)

        def __getitem__(self, index: int) -> dict[str, Any]:
            sample = self.samples[index]
            text = build_model_text(sample, config.input_mode, tokenizer.sep_token or "[SEP]")
            encoded = tokenizer(
                text,
                truncation=True,
                max_length=config.max_length,
                padding="max_length",
                return_tensors="pt",
            )
            item = {key: value.squeeze(0) for key, value in encoded.items()}
            item["risk_label"] = torch.tensor(RISK_TO_ID[sample.risk_label], dtype=torch.long)
            item["alignment_label"] = torch.tensor(sample.alignment_label, dtype=torch.long)
            return item

    train_loader = DataLoader(EncodedDataset(train_samples), batch_size=config.train_batch_size, shuffle=True)
    validation_loader = DataLoader(
        EncodedDataset(validation_samples), batch_size=config.eval_batch_size, shuffle=False
    )
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = create_multitask_model(config.model_name, num_risk_labels=len(RISK_LABELS)).to(device)
    if config.gradient_checkpointing:
        model.encoder.gradient_checkpointing_enable()

    risk_counts = np.bincount(
        [RISK_TO_ID[sample.risk_label] for sample in train_samples], minlength=len(RISK_LABELS)
    )
    risk_weights = risk_counts.sum() / np.maximum(risk_counts, 1) / len(RISK_LABELS)
    risk_loss_fn = nn.CrossEntropyLoss(weight=torch.tensor(risk_weights, dtype=torch.float, device=device))
    alignment_loss_fn = nn.CrossEntropyLoss()
    optimizer = torch.optim.AdamW(model.parameters(), lr=config.learning_rate, weight_decay=config.weight_decay)
    updates_per_epoch = math.ceil(len(train_loader) / config.gradient_accumulation_steps)
    total_updates = max(1, updates_per_epoch * config.epochs)
    scheduler = get_linear_schedule_with_warmup(
        optimizer,
        num_warmup_steps=int(total_updates * config.warmup_ratio),
        num_training_steps=total_updates,
    )
    use_amp = device.type == "cuda" and config.mixed_precision == "fp16"
    scaler = torch.amp.GradScaler("cuda", enabled=use_amp)

    best_macro_f1, stale_epochs = -1.0, 0
    log_records: list[dict[str, Any]] = []
    optimizer.zero_grad(set_to_none=True)
    for epoch in range(1, config.epochs + 1):
        model.train()
        running_loss = 0.0
        for step, batch in enumerate(train_loader, start=1):
            risk_labels = batch.pop("risk_label").to(device)
            alignment_labels = batch.pop("alignment_label").to(device)
            inputs = {key: value.to(device) for key, value in batch.items()}
            with torch.amp.autocast(device_type=device.type, enabled=use_amp):
                output = model(**inputs)
                risk_loss = risk_loss_fn(output["risk_logits"], risk_labels)
                alignment_loss = alignment_loss_fn(output["alignment_logits"], alignment_labels)
                loss = (risk_loss + config.alignment_loss_weight * alignment_loss) / config.gradient_accumulation_steps
            scaler.scale(loss).backward()
            running_loss += float(loss.detach().cpu()) * config.gradient_accumulation_steps
            if step % config.gradient_accumulation_steps == 0 or step == len(train_loader):
                scaler.unscale_(optimizer)
                torch.nn.utils.clip_grad_norm_(model.parameters(), config.max_grad_norm)
                scaler.step(optimizer)
                scaler.update()
                scheduler.step()
                optimizer.zero_grad(set_to_none=True)

        metrics = _validate(model, validation_loader, device, torch)
        record = {"epoch": epoch, "train_loss": running_loss / max(len(train_loader), 1), **metrics}
        log_records.append(record)
        print(json.dumps(record, sort_keys=True))
        if metrics["macro_f1"] > best_macro_f1:
            best_macro_f1 = metrics["macro_f1"]
            stale_epochs = 0
            metadata = ModelMetadata(
                model_name=config.model_name,
                risk_labels=RISK_LABELS,
                input_mode=config.input_mode,
                max_length=config.max_length,
                alignment_loss_weight=config.alignment_loss_weight,
            )
            save_multitask_model(model, tokenizer, metadata, output_dir / "best")
        else:
            stale_epochs += 1
            if stale_epochs >= config.early_stopping_patience:
                break

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "training_log.json").write_text(
        json.dumps(log_records, indent=2) + "\n", encoding="utf-8"
    )
    (output_dir / "resolved_config.json").write_text(
        json.dumps(config.__dict__, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _validate(model: Any, loader: Any, device: Any, torch: Any) -> dict[str, float]:
    model.eval()
    logits: list[np.ndarray] = []
    labels: list[np.ndarray] = []
    with torch.inference_mode():
        for batch in loader:
            risk_labels = batch.pop("risk_label")
            batch.pop("alignment_label")
            output = model(**{key: value.to(device) for key, value in batch.items()})
            logits.append(output["risk_logits"].cpu().numpy())
            labels.append(risk_labels.numpy())
    probabilities = softmax(np.concatenate(logits))
    metrics = evaluate_risk_predictions(np.concatenate(labels), probabilities)
    return {"macro_f1": metrics["macro_f1"], "accuracy": metrics["accuracy"]}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Train the IntentFence multitask encoder")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--train", type=Path, required=True)
    parser.add_argument("--validation", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument(
        "--max-train-samples",
        type=int,
        help="Deterministically cap the train role for an owner-operated smoke run",
    )
    parser.add_argument(
        "--max-validation-samples",
        type=int,
        help="Deterministically cap the validation role for an owner-operated smoke run",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run split/action/coverage preflight without loading ML dependencies or a model",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    config = TrainingConfig.from_yaml(args.config)
    if args.dry_run:
        _, _, summary = load_training_samples(config, args.train, args.validation)
        print(json.dumps({"status": "preflight_passed", **summary.as_dict()}, sort_keys=True))
        return
    if args.output_dir is None:
        parser.error("--output-dir is required unless --dry-run is used")
    train(
        config,
        args.train,
        args.validation,
        args.output_dir,
        max_train_samples=args.max_train_samples,
        max_validation_samples=args.max_validation_samples,
    )


if __name__ == "__main__":
    main()
