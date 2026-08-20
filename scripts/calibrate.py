from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from intentfence.calibration import MultiHeadCalibration, TemperatureScaler
from intentfence.metrics import evaluate_risk_predictions, softmax, threshold_at_fpr


def main() -> None:
    parser = argparse.ArgumentParser(description="Fit independent temperatures on frozen logits")
    parser.add_argument("--logits", type=Path, required=True, help="NPZ with risk_logits, alignment_logits, risk_labels, alignment_labels")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--target-fpr", type=float, default=0.01)
    args = parser.parse_args()
    arrays = np.load(args.logits)
    risk_scaler = TemperatureScaler().fit(arrays["risk_logits"], arrays["risk_labels"])
    alignment_scaler = TemperatureScaler().fit(
        arrays["alignment_logits"], arrays["alignment_labels"]
    )
    calibration = MultiHeadCalibration(risk_scaler, alignment_scaler)
    calibration.save(args.output)

    before = softmax(arrays["risk_logits"])
    after = risk_scaler.predict_proba(arrays["risk_logits"])
    attack_labels = (arrays["risk_labels"] != 0).astype(int)
    attack_scores = 1.0 - after[:, 0]
    report = {
        "before": evaluate_risk_predictions(arrays["risk_labels"], before, target_fpr=args.target_fpr),
        "after": evaluate_risk_predictions(arrays["risk_labels"], after, target_fpr=args.target_fpr),
        "temperatures": {
            "risk": risk_scaler.temperature,
            "alignment": alignment_scaler.temperature,
        },
        "frozen_attack_threshold": threshold_at_fpr(attack_labels, attack_scores, args.target_fpr),
        "target_fpr": args.target_fpr,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report["temperatures"], indent=2))


if __name__ == "__main__":
    main()
