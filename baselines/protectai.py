from __future__ import annotations

import os
from typing import Any


class ProtectAIBaseline:
    model_name = "protectai/deberta-v3-base-prompt-injection-v2"

    def __init__(self, device: int = -1, revision: str | None = None) -> None:
        self.revision = revision or os.getenv("PROTECTAI_MODEL_REVISION")
        if not self.revision:
            raise RuntimeError(
                "Set PROTECTAI_MODEL_REVISION to an immutable Hugging Face commit SHA"
            )
        try:
            from transformers import pipeline
        except ImportError as exc:
            raise RuntimeError("Install intentfence[ml] to run the ProtectAI baseline") from exc
        self.classifier = pipeline(
            "text-classification",
            model=self.model_name,
            tokenizer=self.model_name,
            revision=self.revision,
            device=device,
            top_k=None,
        )

    def attack_scores(self, texts: list[str], batch_size: int = 16) -> list[float]:
        outputs: list[list[dict[str, Any]]] = self.classifier(
            texts, batch_size=batch_size, truncation=True
        )
        scores: list[float] = []
        for candidates in outputs:
            mapping = {str(item["label"]).casefold(): float(item["score"]) for item in candidates}
            attack = next(
                (score for label, score in mapping.items() if label in {"injection", "label_1", "1"}),
                None,
            )
            if attack is None:
                benign = next(
                    (score for label, score in mapping.items() if label in {"legit", "benign", "label_0", "0"}),
                    0.5,
                )
                attack = 1.0 - benign
            scores.append(float(attack))
        return scores
