from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import yaml
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score

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
            if row.get("attack_label") not in {0, 1}:
                raise ValueError(f"Invalid attack_label at {path}:{line_number}")
            score = row.get("attack_score")
            if not isinstance(score, (int, float)) or not np.isfinite(score) or not 0 <= score <= 1:
                raise ValueError(f"Invalid attack_score at {path}:{line_number}")
            rows.append(row)
    if not rows:
        raise ValueError(f"Prediction file is empty: {path}")
    return rows


def _identity(rows: list[dict[str, Any]], path: Path) -> tuple[str, str, str]:
    identities = {
        (str(row.get("backend", "")), str(row.get("revision", "")), str(row.get("split", "")))
        for row in rows
    }
    if len(identities) != 1:
        raise ValueError(f"Prediction identity is not unique in {path}: {sorted(identities)}")
    backend, revision, split = identities.pop()
    if not backend or not revision or not split:
        raise ValueError(f"Prediction identity is incomplete in {path}")
    return backend, revision, split


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _binary_diagnostics(rows: list[dict[str, Any]]) -> dict[str, float | str]:
    labels = np.asarray([row["attack_label"] for row in rows], dtype=int)
    scores = np.asarray([row["attack_score"] for row in rows], dtype=float)
    if len(np.unique(labels)) < 2:
        return {
            "status": "insufficient_class_coverage",
            "attack_brier": float(brier_score_loss(labels, scores)),
        }
    return {
        "status": "available",
        "attack_auroc": float(roc_auc_score(labels, scores)),
        "attack_auprc": float(average_precision_score(labels, scores)),
        "attack_brier": float(brier_score_loss(labels, scores)),
    }


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
        "test_diagnostics": _binary_diagnostics(test_rows),
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
    parser.add_argument(
        "--default-threshold",
        type=float,
        help="Optional upstream/default threshold reported separately from the frozen threshold",
    )
    parser.add_argument(
        "--protocol-registry",
        type=Path,
        default=Path("configs/experiment_registry.yaml"),
    )
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"Refusing to overwrite {args.output}")
    calibration_rows, test_rows = _read(args.calibration), _read(args.test)
    calibration_identity = _identity(calibration_rows, args.calibration)
    test_identity = _identity(test_rows, args.test)
    if calibration_identity[:2] != test_identity[:2]:
        raise ValueError(
            "Calibration and test predictions must use the same backend and immutable revision"
        )
    if calibration_identity[2] != "calibration":
        raise ValueError(
            f"Calibration predictions declare split={calibration_identity[2]!r}, not 'calibration'"
        )
    if test_identity[2] == "calibration":
        raise ValueError("Test predictions cannot declare the calibration split")
    overlap = {row["sample_id"] for row in calibration_rows} & {
        row["sample_id"] for row in test_rows
    }
    if overlap:
        raise ValueError(f"Calibration and test predictions overlap: {sorted(overlap)[:10]}")
    if {row["attack_label"] for row in calibration_rows} != {0, 1}:
        raise ValueError("Calibration predictions require both benign and attack rows")
    protocol = yaml.safe_load(args.protocol_registry.read_text(encoding="utf-8"))
    if not isinstance(protocol, dict) or protocol.get("status") != "frozen":
        raise ValueError("Baseline evaluation requires a frozen experiment registry")
    result = evaluate_frozen_threshold(
        calibration_rows, test_rows, args.target_fpr, args.minimum_tpr
    )
    result.update(
        {
            "schema_version": 1,
            "protocol_version": protocol.get("protocol_version"),
            "backend": calibration_identity[0],
            "revision": calibration_identity[1],
            "calibration_split": calibration_identity[2],
            "test_split": test_identity[2],
            "calibration_rows": len(calibration_rows),
            "test_rows": len(test_rows),
            "calibration_predictions_sha256": _sha256(args.calibration),
            "test_predictions_sha256": _sha256(args.test),
        }
    )
    if args.default_threshold is not None:
        if not 0 <= args.default_threshold <= 1:
            raise ValueError("--default-threshold must be in [0, 1]")
        labels = np.asarray([row["attack_label"] for row in test_rows], dtype=int)
        scores = np.asarray([row["attack_score"] for row in test_rows], dtype=float)
        result["default_threshold_test"] = binary_operating_point(
            labels, scores, args.default_threshold
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
