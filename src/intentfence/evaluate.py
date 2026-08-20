from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from intentfence.constants import RISK_TO_ID
from intentfence.inference import RuleBackend, TorchBackend
from intentfence.metrics import evaluate_risk_predictions
from intentfence.schema import read_jsonl


def evaluate_dataset(backend: RuleBackend | TorchBackend, input_path: Path, output_dir: Path) -> dict:
    samples = read_jsonl(input_path)
    records: list[dict] = []
    probabilities: list[list[float]] = []
    labels: list[int] = []
    for sample in samples:
        prediction = backend.predict(sample.user_goal, sample.untrusted_content, sample.proposed_action)
        labels.append(RISK_TO_ID[sample.risk_label])
        probabilities.append([prediction.probabilities[label] for label in RISK_TO_ID])
        records.append(
            {
                "sample_id": sample.sample_id,
                "true_risk": sample.risk_label,
                "predicted_risk": prediction.predicted_risk,
                "attack_score": prediction.attack_score,
                "alignment_conflict_probability": prediction.alignment_conflict_probability,
                "risk_probabilities": prediction.probabilities,
                "backend": prediction.backend,
                "calibrated": prediction.calibrated,
            }
        )
    metrics = evaluate_risk_predictions(np.array(labels), np.array(probabilities))
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "predictions.jsonl").write_text(
        "".join(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n" for record in records),
        encoding="utf-8",
    )
    (output_dir / "metrics.json").write_text(
        json.dumps(metrics, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return metrics


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate an IntentFence backend")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--backend", choices=("rules", "torch"), default="rules")
    parser.add_argument("--model-dir", type=Path)
    parser.add_argument("--calibration", type=Path)
    args = parser.parse_args()
    if args.backend == "torch":
        if args.model_dir is None:
            parser.error("--model-dir is required for --backend torch")
        backend = TorchBackend(args.model_dir, args.calibration)
    else:
        backend = RuleBackend()
    print(json.dumps(evaluate_dataset(backend, args.input, args.output_dir), indent=2))


if __name__ == "__main__":
    main()
