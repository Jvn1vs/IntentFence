from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np

from intentfence.metrics import binary_operating_point, threshold_at_fpr


def _read(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            row = json.loads(line)
            sample_id = row["sample_id"]
            if sample_id in seen:
                raise ValueError(f"Duplicate sample_id at {path}:{line_number}: {sample_id}")
            seen.add(sample_id)
            rows.append(row)
    return rows


def evaluate_frozen_threshold(
    calibration_rows: list[dict[str, Any]],
    test_rows: list[dict[str, Any]],
    target_fpr: float,
    minimum_tpr: float,
) -> dict[str, Any]:
    cal_labels = np.asarray([row["attack_label"] for row in calibration_rows], dtype=int)
    cal_scores = np.asarray([row["attack_score"] for row in calibration_rows], dtype=float)
    test_labels = np.asarray([row["attack_label"] for row in test_rows], dtype=int)
    test_scores = np.asarray([row["attack_score"] for row in test_rows], dtype=float)
    threshold = threshold_at_fpr(cal_labels, cal_scores, target_fpr)
    calibration = binary_operating_point(cal_labels, cal_scores, threshold)
    test = binary_operating_point(test_labels, test_scores, threshold)
    return {
        "threshold_source": "calibration_only",
        "target_fpr": target_fpr,
        "minimum_viable_attack_tpr": minimum_tpr,
        "threshold": threshold,
        "calibration": calibration,
        "test": test,
        "operational_failure": calibration["tpr"] < minimum_tpr,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate baseline scores at a calibration-only frozen threshold"
    )
    parser.add_argument("--calibration", type=Path, required=True)
    parser.add_argument("--test", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--target-fpr", type=float, default=0.01)
    parser.add_argument("--minimum-tpr", type=float, default=0.80)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"Refusing to overwrite {args.output}")
    result = evaluate_frozen_threshold(
        _read(args.calibration), _read(args.test), args.target_fpr, args.minimum_tpr
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
