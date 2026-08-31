from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from intentfence.constants import LEGACY_ALIGNMENT_LABELS


@dataclass(frozen=True)
class ModelMetadata:
    model_name: str
    risk_labels: tuple[str, ...]
    input_mode: str
    max_length: int
    alignment_loss_weight: float
    model_revision: str | None = None
    version: str = "2"
    alignment_labels: tuple[str, ...] = LEGACY_ALIGNMENT_LABELS
    alignment_target: str = "legacy_binary"


def _require_ml() -> tuple[Any, Any, Any]:
    try:
        import torch
        from torch import nn
        from transformers import AutoModel
    except ImportError as exc:
        raise RuntimeError(
            "Training support is not installed. Run: python -m pip install -e '.[ml]'"
        ) from exc
    return torch, nn, AutoModel


def create_multitask_model(
    model_name: str,
    *,
    revision: str | None = None,
    num_risk_labels: int = 5,
    num_alignment_labels: int = 2,
    dropout: float | None = None,
) -> Any:
    torch, nn, AutoModel = _require_ml()

    class MultiTaskIntentFence(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            model_kwargs = {"revision": revision} if revision is not None else {}
            self.encoder = AutoModel.from_pretrained(model_name, **model_kwargs)
            hidden_size = int(self.encoder.config.hidden_size)
            probability = float(
                dropout
                if dropout is not None
                else getattr(self.encoder.config, "hidden_dropout_prob", 0.1)
            )
            self.dropout = nn.Dropout(probability)
            self.risk_head = nn.Linear(hidden_size, num_risk_labels)
            self.alignment_head = nn.Linear(hidden_size, num_alignment_labels)

        def forward(
            self,
            input_ids: Any,
            attention_mask: Any,
            token_type_ids: Any | None = None,
        ) -> dict[str, Any]:
            kwargs = {"input_ids": input_ids, "attention_mask": attention_mask}
            if token_type_ids is not None and getattr(self.encoder.config, "type_vocab_size", 0) > 0:
                kwargs["token_type_ids"] = token_type_ids
            output = self.encoder(**kwargs)
            pooled = self.dropout(output.last_hidden_state[:, 0])
            return {
                "risk_logits": self.risk_head(pooled),
                "alignment_logits": self.alignment_head(pooled),
            }

    return MultiTaskIntentFence()


def save_multitask_model(
    model: Any,
    tokenizer: Any,
    metadata: ModelMetadata,
    output_dir: str | Path,
) -> None:
    torch, _, _ = _require_ml()
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    model.encoder.save_pretrained(destination / "encoder")
    tokenizer.save_pretrained(destination / "tokenizer")
    torch.save(
        {
            "risk_head": model.risk_head.state_dict(),
            "alignment_head": model.alignment_head.state_dict(),
            "dropout_probability": model.dropout.p,
        },
        destination / "heads.pt",
    )
    (destination / "metadata.json").write_text(
        json.dumps(asdict(metadata), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def load_multitask_model(model_dir: str | Path, *, map_location: str = "cpu") -> tuple[Any, Any, ModelMetadata]:
    torch, _, _ = _require_ml()
    try:
        from transformers import AutoTokenizer
    except ImportError as exc:
        raise RuntimeError("Install the ml extra to load a trained model") from exc

    source = Path(model_dir)
    metadata_payload = json.loads((source / "metadata.json").read_text(encoding="utf-8"))
    metadata_payload["risk_labels"] = tuple(metadata_payload["risk_labels"])
    metadata_payload["alignment_labels"] = tuple(
        metadata_payload.get("alignment_labels", LEGACY_ALIGNMENT_LABELS)
    )
    metadata_payload.setdefault("alignment_target", "legacy_binary")
    metadata = ModelMetadata(**metadata_payload)
    model = create_multitask_model(
        str(source / "encoder"),
        num_risk_labels=len(metadata.risk_labels),
        num_alignment_labels=len(metadata.alignment_labels),
    )
    heads = torch.load(source / "heads.pt", map_location=map_location, weights_only=True)
    model.risk_head.load_state_dict(heads["risk_head"])
    model.alignment_head.load_state_dict(heads["alignment_head"])
    model.dropout.p = float(heads.get("dropout_probability", model.dropout.p))
    tokenizer = AutoTokenizer.from_pretrained(source / "tokenizer")
    return model, tokenizer, metadata
