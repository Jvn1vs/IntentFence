from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from scipy.optimize import minimize_scalar
from sklearn.metrics import log_loss

from intentfence.metrics import softmax


@dataclass
class TemperatureScaler:
    temperature: float = 1.0

    def fit(self, logits: np.ndarray, labels: np.ndarray) -> TemperatureScaler:
        logits = np.asarray(logits, dtype=float)
        labels = np.asarray(labels, dtype=int)
        if logits.ndim != 2 or logits.shape[0] != labels.shape[0]:
            raise ValueError("logits must be [samples, classes] and match labels")
        if logits.shape[0] < 2:
            raise ValueError("At least two calibration samples are required")

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
        return np.asarray(logits, dtype=float) / self.temperature

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
        return cls(
            risk=TemperatureScaler.from_dict(payload["risk"]),
            alignment=TemperatureScaler.from_dict(payload["alignment"]),
            version=str(payload.get("version", "1")),
        )
