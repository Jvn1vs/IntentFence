from __future__ import annotations

import os


class PIGuardBaseline:
    """Adapter for an InjecGuard/PIGuard-compatible Hugging Face checkpoint.

    The upstream project has changed checkpoint packaging over time, so the exact
    immutable model revision is supplied explicitly through environment/config.
    """

    def __init__(
        self,
        model_name: str | None = None,
        revision: str | None = None,
        device: int = -1,
    ) -> None:
        self.model_name = model_name or os.getenv("PIGUARD_MODEL_ID")
        self.revision = revision or os.getenv("PIGUARD_MODEL_REVISION")
        if not self.model_name:
            raise RuntimeError("Set PIGUARD_MODEL_ID to the pinned upstream checkpoint revision")
        if not self.revision:
            raise RuntimeError("Set PIGUARD_MODEL_REVISION to an immutable commit SHA")
        try:
            from transformers import pipeline
        except ImportError as exc:
            raise RuntimeError("Install intentfence[ml] to run the PIGuard baseline") from exc
        self.classifier = pipeline(
            "text-classification",
            model=self.model_name,
            tokenizer=self.model_name,
            revision=self.revision,
            device=device,
            top_k=None,
            trust_remote_code=True,
        )

    def attack_scores(self, texts: list[str], batch_size: int = 16) -> list[float]:
        outputs = self.classifier(texts, batch_size=batch_size, truncation=True)
        result: list[float] = []
        for candidates in outputs:
            mapping = {str(item["label"]).casefold(): float(item["score"]) for item in candidates}
            attack = max(
                (
                    score
                    for label, score in mapping.items()
                    if label not in {"benign", "legit", "label_0", "0"}
                ),
                default=1.0 - mapping.get("benign", mapping.get("label_0", 0.5)),
            )
            result.append(float(attack))
        return result
