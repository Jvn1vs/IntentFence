from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from intentfence.calibration import MultiHeadCalibration
from intentfence.metrics import evaluate_risk_predictions, softmax


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare calibration before and after scaling")
    parser.add_argument("--logits", type=Path, required=True)
    parser.add_argument("--calibration", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    arrays = np.load(args.logits)
    scaler = MultiHeadCalibration.load(args.calibration)
    result = {
        "before": evaluate_risk_predictions(arrays["risk_labels"], softmax(arrays["risk_logits"])),
        "after": evaluate_risk_predictions(
            arrays["risk_labels"], scaler.risk.predict_proba(arrays["risk_logits"])
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
