from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import numpy as np

from intentfence.calibration import MultiHeadCalibration
from intentfence.constants import LEGACY_ALIGNMENT_LABELS, RISK_LABELS
from intentfence.deployment import validate_export_artifacts
from intentfence.metrics import softmax
from intentfence.modeling import load_multitask_model
from intentfence.rules import RuleDetector
from intentfence.text import build_text_from_fields, chunk_untrusted_content


def _alignment_conflict_probability(
    probabilities: np.ndarray,
    labels: tuple[str, ...],
) -> float:
    mapping = dict(zip(labels, probabilities.tolist(), strict=True))
    if "conflict" in mapping:
        return float(mapping["conflict"])
    if "aligned" in mapping:
        return float(1.0 - mapping["aligned"])
    raise ValueError(f"alignment labels lack aligned/conflict semantics: {labels}")


@dataclass(frozen=True)
class BackendPrediction:
    probabilities: dict[str, float]
    alignment_conflict_probability: float
    predicted_risk: str
    attack_score: float
    backend: str
    calibrated: bool
    evidence: tuple[str, ...] = ()
    document_level: bool = False


class InferenceBackend(Protocol):
    name: str
    model_version: str
    model_revision: str | None

    def predict(self, user_goal: str, untrusted_content: str, proposed_action: str) -> BackendPrediction: ...


class RuleBackend:
    name = "rules-v1"
    model_version = name
    model_revision = None

    def __init__(self) -> None:
        self.detector = RuleDetector()

    def predict(self, user_goal: str, untrusted_content: str, proposed_action: str) -> BackendPrediction:
        chunks = chunk_untrusted_content(untrusted_content)
        predictions = [self.detector.predict(user_goal, chunk, proposed_action) for chunk in chunks]
        chosen = max(predictions, key=lambda item: item.attack_score)
        evidence = tuple(dict.fromkeys(hit.rule_id for item in predictions for hit in item.hits))
        return BackendPrediction(
            probabilities=chosen.probabilities,
            alignment_conflict_probability=chosen.alignment_conflict_probability,
            predicted_risk=chosen.predicted_risk,
            attack_score=chosen.attack_score,
            backend=self.name,
            calibrated=False,
            evidence=evidence,
            document_level=len(chunks) > 1,
        )


class TorchBackend:
    name = "torch-deberta"

    def __init__(
        self,
        model_dir: str | Path,
        calibration_path: str | Path | None = None,
        device: str = "cpu",
    ) -> None:
        try:
            import torch
        except ImportError as exc:
            raise RuntimeError("Install intentfence[ml] for PyTorch inference") from exc
        self.torch = torch
        self.model, self.tokenizer, self.metadata = load_multitask_model(
            model_dir, map_location=device
        )
        self.model.to(device).eval()
        self.device = device
        self.model_revision = self.metadata.model_revision
        self.model_version = self.metadata.model_revision or self.metadata.version
        self.calibration = (
            MultiHeadCalibration.load(calibration_path) if calibration_path and Path(calibration_path).exists() else None
        )

    def predict(self, user_goal: str, untrusted_content: str, proposed_action: str) -> BackendPrediction:
        separator = self.tokenizer.sep_token or "[SEP]"
        text = build_text_from_fields(user_goal, untrusted_content, proposed_action, separator)
        encoded = self.tokenizer(
            text,
            truncation=True,
            max_length=self.metadata.max_length,
            return_tensors="pt",
        )
        encoded = {key: value.to(self.device) for key, value in encoded.items()}
        with self.torch.inference_mode():
            output = self.model(**encoded)
        risk_logits = output["risk_logits"].detach().cpu().numpy()
        alignment_logits = output["alignment_logits"].detach().cpu().numpy()
        if self.calibration:
            risk_probabilities = self.calibration.risk.predict_proba(risk_logits)[0]
            alignment_probabilities = self.calibration.alignment.predict_proba(alignment_logits)[0]
        else:
            risk_probabilities = softmax(risk_logits)[0]
            alignment_probabilities = softmax(alignment_logits)[0]
        mapping = dict(zip(self.metadata.risk_labels, risk_probabilities.tolist(), strict=True))
        predicted = max(mapping, key=mapping.get)
        return BackendPrediction(
            probabilities=mapping,
            alignment_conflict_probability=_alignment_conflict_probability(
                alignment_probabilities, self.metadata.alignment_labels
            ),
            predicted_risk=predicted,
            attack_score=float(1.0 - mapping["benign"]),
            backend=self.name,
            calibrated=self.calibration is not None,
        )


class OnnxBackend:
    name = "onnx-deberta"

    def __init__(
        self,
        model_path: str | Path,
        tokenizer_path: str | Path,
        calibration_path: str | Path | None = None,
        max_length: int = 384,
        metadata_path: str | Path | None = None,
    ) -> None:
        model_path = Path(model_path)
        inferred_metadata = Path(metadata_path) if metadata_path else model_path.parent / "export_metadata.json"
        export_metadata = None
        if inferred_metadata.exists():
            export_metadata = validate_export_artifacts(
                inferred_metadata.parent,
                model_path=model_path,
            )
            expected_tokenizer = inferred_metadata.parent / "tokenizer"
            if Path(tokenizer_path).resolve() != expected_tokenizer.resolve():
                raise ValueError("tokenizer_path does not match the hash-bound export tokenizer")
        try:
            import onnxruntime as ort
            from transformers import AutoTokenizer
        except ImportError as exc:
            raise RuntimeError("Install intentfence[ml,onnx] for ONNX inference") from exc
        self.session = ort.InferenceSession(str(model_path), providers=["CPUExecutionProvider"])
        self.tokenizer = AutoTokenizer.from_pretrained(tokenizer_path)
        self.calibration = (
            MultiHeadCalibration.load(calibration_path) if calibration_path and Path(calibration_path).exists() else None
        )
        if export_metadata is not None:
            export = export_metadata["export"]
            self.risk_labels = tuple(export["risk_labels"])
            self.alignment_labels = tuple(export["alignment_labels"])
            self.max_length = int(export["max_length"])
            self.model_revision = str(export_metadata["source_model"]["model_revision"])
            self.model_version = self.model_revision
        else:
            self.risk_labels = RISK_LABELS
            self.alignment_labels = LEGACY_ALIGNMENT_LABELS
            self.max_length = max_length
            self.model_revision = None
            self.model_version = model_path.stem

    def predict(self, user_goal: str, untrusted_content: str, proposed_action: str) -> BackendPrediction:
        separator = self.tokenizer.sep_token or "[SEP]"
        text = build_text_from_fields(user_goal, untrusted_content, proposed_action, separator)
        encoded = self.tokenizer(
            text,
            truncation=True,
            max_length=self.max_length,
            return_tensors="np",
        )
        names = {item.name for item in self.session.get_inputs()}
        feed = {key: value.astype(np.int64) for key, value in encoded.items() if key in names}
        risk_logits, alignment_logits = self.session.run(None, feed)
        risk_probabilities = (
            self.calibration.risk.predict_proba(risk_logits)[0]
            if self.calibration
            else softmax(risk_logits)[0]
        )
        alignment_probabilities = (
            self.calibration.alignment.predict_proba(alignment_logits)[0]
            if self.calibration
            else softmax(alignment_logits)[0]
        )
        mapping = dict(zip(self.risk_labels, risk_probabilities.tolist(), strict=True))
        predicted = max(mapping, key=mapping.get)
        return BackendPrediction(
            probabilities=mapping,
            alignment_conflict_probability=_alignment_conflict_probability(
                alignment_probabilities, self.alignment_labels
            ),
            predicted_risk=predicted,
            attack_score=float(1.0 - mapping["benign"]),
            backend=self.name,
            calibrated=self.calibration is not None,
        )
