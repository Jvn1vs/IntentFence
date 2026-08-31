from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
from scipy.optimize import minimize_scalar
from sklearn.metrics import log_loss

from intentfence.constants import LEGACY_ALIGNMENT_LABELS, RISK_LABELS, TASK_ALIGNMENT_LABELS
from intentfence.metrics import softmax
from intentfence.run_manifest import sha256_file

CALIBRATION_ARRAY_NAMES = (
    "risk_logits",
    "alignment_logits",
    "risk_labels",
    "alignment_labels",
)


def _integer_labels(value: Any, *, name: str, class_count: int) -> np.ndarray:
    raw = np.asarray(value)
    if raw.ndim != 1:
        raise ValueError(f"{name} must be one-dimensional")
    try:
        numeric = np.asarray(raw, dtype=float)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must contain integer class ids") from exc
    if (
        not np.isfinite(numeric).all()
        or not np.equal(numeric, np.floor(numeric)).all()
    ):
        raise ValueError(f"{name} must contain integer class ids")
    labels = numeric.astype(int)
    if np.any(labels < 0) or np.any(labels >= class_count):
        raise ValueError(f"{name} contains a class id outside [0, {class_count})")
    return labels


def validate_calibration_arrays(arrays: Mapping[str, Any]) -> dict[str, int]:
    """Validate the frozen-model logits contract before any calibration fit."""

    missing = [name for name in CALIBRATION_ARRAY_NAMES if name not in arrays]
    if missing:
        raise ValueError(f"calibration logits are missing arrays: {missing}")
    risk_logits = np.asarray(arrays["risk_logits"], dtype=float)
    alignment_logits = np.asarray(arrays["alignment_logits"], dtype=float)
    if (
        risk_logits.ndim != 2
        or risk_logits.shape[0] == 0
        or risk_logits.shape[1] != len(RISK_LABELS)
    ):
        raise ValueError(f"risk_logits must have shape [samples, {len(RISK_LABELS)}]")
    if (
        alignment_logits.ndim != 2
        or alignment_logits.shape[0] != risk_logits.shape[0]
        or alignment_logits.shape[1] not in (2, len(TASK_ALIGNMENT_LABELS))
    ):
        raise ValueError(
            "alignment_logits must have shape [samples, 2] or "
            f"[samples, {len(TASK_ALIGNMENT_LABELS)}]"
        )
    if not np.isfinite(risk_logits).all() or not np.isfinite(alignment_logits).all():
        raise ValueError("calibration logits must contain only finite values")
    risk_labels = _integer_labels(
        arrays["risk_labels"], name="risk_labels", class_count=len(RISK_LABELS)
    )
    alignment_labels = _integer_labels(
        arrays["alignment_labels"],
        name="alignment_labels",
        class_count=alignment_logits.shape[1],
    )
    if len(risk_labels) != len(risk_logits) or len(alignment_labels) != len(risk_logits):
        raise ValueError("logit and label arrays must contain the same number of samples")
    if len(np.unique(risk_labels)) < 2:
        raise ValueError("risk_labels must contain at least two classes for calibration")
    if not np.any(risk_labels == 0) or not np.any(risk_labels != 0):
        raise ValueError("risk_labels must contain benign and attack samples for FPR calibration")
    if len(np.unique(alignment_labels)) < 2:
        raise ValueError("alignment_labels must contain at least two classes for calibration")
    return {
        "samples": int(len(risk_labels)),
        "risk_classes": int(risk_logits.shape[1]),
        "alignment_classes": int(alignment_logits.shape[1]),
    }


def load_calibration_arrays(
    logits_path: str | Path, metadata_path: str | Path | None = None
) -> tuple[dict[str, np.ndarray], dict[str, Any]]:
    """Load logits and require a matching, hash-verified calibration sidecar."""

    logits_path = Path(logits_path)
    if not logits_path.is_file():
        raise FileNotFoundError(f"calibration logits do not exist: {logits_path}")
    metadata_path = Path(metadata_path) if metadata_path is not None else logits_path.with_suffix(".json")
    if not metadata_path.is_file():
        raise FileNotFoundError(f"calibration metadata does not exist: {metadata_path}")
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid calibration metadata JSON: {metadata_path}") from exc
    if not isinstance(metadata, dict):
        raise ValueError("calibration metadata must be a JSON object")
    if metadata.get("split") != "calibration":
        raise ValueError("calibration logits must be exported from split='calibration'")
    input_value = metadata.get("input")
    input_sha256 = metadata.get("input_sha256")
    if not isinstance(input_value, str) or not input_value:
        raise ValueError("calibration metadata must identify the input file")
    if not isinstance(input_sha256, str) or len(input_sha256) != 64:
        raise ValueError("calibration metadata must include a 64-character input_sha256")
    input_path = Path(input_value)
    if not input_path.is_absolute():
        input_path = metadata_path.parent / input_path
    if not input_path.is_file():
        raise FileNotFoundError(f"calibration input from metadata does not exist: {input_path}")
    if sha256_file(input_path) != input_sha256:
        raise ValueError("calibration input hash does not match metadata")
    with np.load(logits_path, allow_pickle=False) as loaded:
        arrays = {name: np.asarray(loaded[name]).copy() for name in CALIBRATION_ARRAY_NAMES if name in loaded}
    summary = validate_calibration_arrays(arrays)
    if metadata.get("samples") != summary["samples"]:
        raise ValueError("calibration metadata sample count does not match logits")
    expected_shapes = {
        "risk_logits": [summary["samples"], summary["risk_classes"]],
        "alignment_logits": [summary["samples"], summary["alignment_classes"]],
    }
    for name, shape in expected_shapes.items():
        recorded = metadata.get(f"{name}_shape")
        if recorded is not None and recorded != shape:
            raise ValueError(f"calibration metadata shape for {name} does not match logits")
    if metadata.get("risk_labels") != list(RISK_LABELS):
        raise ValueError("calibration metadata risk_labels do not match the frozen label contract")
    expected_alignment_labels = list(
        TASK_ALIGNMENT_LABELS if summary["alignment_classes"] == 4 else LEGACY_ALIGNMENT_LABELS
    )
    if metadata.get("alignment_labels") != expected_alignment_labels:
        raise ValueError(
            "calibration metadata alignment_labels do not match the logits class count"
        )
    return arrays, metadata


def validate_calibration_authorization(
    authorization_path: str | Path,
    *,
    logits_path: str | Path,
    metadata: Mapping[str, Any],
) -> dict[str, Any]:
    """Require project-owner authorization tied to this exact calibration input."""

    authorization_path = Path(authorization_path)
    if not authorization_path.is_file():
        raise FileNotFoundError(f"calibration authorization does not exist: {authorization_path}")
    try:
        payload = json.loads(authorization_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("calibration authorization must be valid JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("calibration authorization must be a JSON object")
    if payload.get("calibration_authorized") is not True:
        raise ValueError("calibration authorization requires calibration_authorized=true")
    if payload.get("human_verified") is not True:
        raise ValueError("calibration authorization requires independent human_verified=true")
    if payload.get("final_test_lock_preserved") is not True:
        raise ValueError("calibration authorization must preserve the final-test lock")
    if not isinstance(payload.get("approved_by_project_owner"), str) or not payload[
        "approved_by_project_owner"
    ].strip():
        raise ValueError("calibration authorization requires approved_by_project_owner")
    approved_at = payload.get("approved_at")
    if not isinstance(approved_at, str) or not re.search(r"(?:Z|[+-]\d{2}:\d{2})$", approved_at):
        raise ValueError("calibration authorization approved_at must include a timezone")
    try:
        parsed_timestamp = datetime.fromisoformat(approved_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("calibration authorization approved_at must be ISO-8601") from exc
    if parsed_timestamp.tzinfo is None:
        raise ValueError("calibration authorization approved_at must include a timezone")

    expected_logits_sha256 = sha256_file(logits_path)
    if payload.get("logits_sha256") != expected_logits_sha256:
        raise ValueError("calibration authorization logits_sha256 does not match the NPZ")
    if payload.get("input_sha256") != metadata.get("input_sha256"):
        raise ValueError("calibration authorization input_sha256 does not match metadata")
    if payload.get("model_dir") != metadata.get("model_dir"):
        raise ValueError("calibration authorization model_dir does not match metadata")
    return payload


@dataclass
class TemperatureScaler:
    temperature: float = 1.0

    def __post_init__(self) -> None:
        if not np.isfinite(self.temperature) or self.temperature <= 0:
            raise ValueError("temperature must be positive and finite")

    def fit(self, logits: np.ndarray, labels: np.ndarray) -> TemperatureScaler:
        logits = np.asarray(logits, dtype=float)
        if logits.ndim != 2 or logits.shape[0] == 0:
            raise ValueError("logits must be a non-empty [samples, classes] array")
        if not np.isfinite(logits).all():
            raise ValueError("logits must contain only finite values")
        labels = _integer_labels(labels, name="labels", class_count=logits.shape[1])
        if logits.shape[0] != labels.shape[0]:
            raise ValueError("logits must be [samples, classes] and match labels")
        if logits.shape[0] < 2:
            raise ValueError("At least two calibration samples are required")
        if len(np.unique(labels)) < 2:
            raise ValueError("At least two label classes are required for calibration")

        def objective(log_temperature: float) -> float:
            temperature = float(np.exp(log_temperature))
            probabilities = softmax(logits / temperature)
            return float(log_loss(labels, probabilities, labels=list(range(logits.shape[1]))))

        result = minimize_scalar(objective, bounds=(-4.0, 4.0), method="bounded")
        if not result.success:
            raise RuntimeError(f"Temperature optimization failed: {result.message}")
        self.temperature = float(np.exp(result.x))
        return self

    def transform_logits(self, logits: np.ndarray) -> np.ndarray:
        if self.temperature <= 0:
            raise ValueError("temperature must be positive")
        logits = np.asarray(logits, dtype=float)
        if logits.ndim != 2 or logits.shape[0] == 0 or not np.isfinite(logits).all():
            raise ValueError("logits must be a non-empty finite [samples, classes] array")
        return logits / self.temperature

    def predict_proba(self, logits: np.ndarray) -> np.ndarray:
        return softmax(self.transform_logits(logits))

    def to_dict(self) -> dict[str, float]:
        return {"temperature": self.temperature}

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> TemperatureScaler:
        return cls(temperature=float(payload["temperature"]))


@dataclass
class MultiHeadCalibration:
    risk: TemperatureScaler
    alignment: TemperatureScaler
    version: str = "1"

    def save(self, path: str | Path) -> None:
        output = Path(path)
        if output.exists():
            raise FileExistsError(f"refusing to overwrite calibration file: {output}")
        output.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": self.version,
            "risk": self.risk.to_dict(),
            "alignment": self.alignment.to_dict(),
        }
        output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> MultiHeadCalibration:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("calibration file must contain a JSON object")
        return cls(
            risk=TemperatureScaler.from_dict(payload["risk"]),
            alignment=TemperatureScaler.from_dict(payload["alignment"]),
            version=str(payload.get("version", "1")),
        )
