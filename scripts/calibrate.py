from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from intentfence.calibration import (
    MultiHeadCalibration,
    TemperatureScaler,
    load_calibration_arrays,
    validate_calibration_arrays,
    validate_calibration_authorization,
)
from intentfence.constants import RISK_LABELS
from intentfence.metrics import (
    binary_operating_point,
    calibration_metrics,
    softmax,
    threshold_at_fpr,
)
from intentfence.run_manifest import sha256_file


def _ensure_new_outputs(output: Path, report: Path) -> None:
    if output.resolve() == report.resolve():
        raise ValueError("calibration output and report must be different files")
    occupied = [str(path) for path in (output, report) if path.exists()]
    if occupied:
        raise FileExistsError(f"refusing to overwrite existing calibration outputs: {occupied}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fit independent temperatures on frozen calibration logits"
    )
    parser.add_argument(
        "--logits",
        type=Path,
        required=True,
        help="NPZ with risk_logits, alignment_logits, risk_labels, alignment_labels",
    )
    parser.add_argument("--output", type=Path, required=True, help="versioned calibration JSON")
    parser.add_argument("--report", type=Path, required=True, help="calibration-only report JSON")
    parser.add_argument("--target-fpr", type=float, default=0.01)
    parser.add_argument("--n-bins", type=int, default=15)
    parser.add_argument("--classwise-min-samples", type=int, default=10)
    parser.add_argument(
        "--authorization-file",
        type=Path,
        help="project-owner authorization tied to this exact frozen logits bundle",
    )
    parser.add_argument(
        "--preflight-only",
        action="store_true",
        help="validate the calibration NPZ and sidecar without fitting or writing files",
    )
    args = parser.parse_args()

    if not 0 <= args.target_fpr < 1:
        raise SystemExit("--target-fpr must be in [0, 1)")
    if args.n_bins <= 0:
        raise SystemExit("--n-bins must be positive")
    if args.classwise_min_samples <= 0:
        raise SystemExit("--classwise-min-samples must be positive")

    metadata_path = args.logits.with_suffix(".json")
    try:
        arrays, metadata = load_calibration_arrays(args.logits, metadata_path)
        summary = validate_calibration_arrays(arrays)
        _ensure_new_outputs(args.output, args.report)
    except (FileNotFoundError, OSError, ValueError) as exc:
        raise SystemExit(f"calibration preflight failed: {exc}") from exc

    if args.preflight_only:
        print(
            json.dumps(
                {
                    "status": "preflight_passed",
                    "split": metadata["split"],
                    "summary": summary,
                    "logits": str(args.logits.resolve()),
                    "metadata": str(metadata_path.resolve()),
                },
                indent=2,
                sort_keys=True,
            )
        )
        return

    if args.authorization_file is None:
        raise SystemExit(
            "calibration authorization is required for fitting; use --preflight-only for a read-only check"
        )
    try:
        authorization = validate_calibration_authorization(
            args.authorization_file,
            logits_path=args.logits,
            metadata=metadata,
        )
    except (FileNotFoundError, OSError, ValueError) as exc:
        raise SystemExit(f"calibration authorization failed: {exc}") from exc

    risk_labels = arrays["risk_labels"]
    risk_scaler = TemperatureScaler().fit(arrays["risk_logits"], risk_labels)
    alignment_scaler = TemperatureScaler().fit(
        arrays["alignment_logits"], arrays["alignment_labels"]
    )
    calibration = MultiHeadCalibration(risk_scaler, alignment_scaler)

    risk_before = softmax(arrays["risk_logits"])
    risk_after = risk_scaler.predict_proba(arrays["risk_logits"])
    alignment_before = softmax(arrays["alignment_logits"])
    alignment_after = alignment_scaler.predict_proba(arrays["alignment_logits"])
    attack_labels = (risk_labels != 0).astype(int)
    attack_scores = 1.0 - risk_after[:, 0]
    frozen_threshold = threshold_at_fpr(attack_labels, attack_scores, args.target_fpr)
    risk_before_metrics = calibration_metrics(
        risk_before,
        risk_labels,
        n_bins=args.n_bins,
        min_class_samples=args.classwise_min_samples,
    )
    risk_after_metrics = calibration_metrics(
        risk_after,
        risk_labels,
        n_bins=args.n_bins,
        min_class_samples=args.classwise_min_samples,
    )
    alignment_before_metrics = calibration_metrics(
        alignment_before,
        arrays["alignment_labels"],
        n_bins=args.n_bins,
        min_class_samples=args.classwise_min_samples,
    )
    alignment_after_metrics = calibration_metrics(
        alignment_after,
        arrays["alignment_labels"],
        n_bins=args.n_bins,
        min_class_samples=args.classwise_min_samples,
    )
    ranking_unchanged = {
        "risk": bool(
            np.array_equal(
                np.argsort(arrays["risk_logits"], axis=1),
                np.argsort(risk_scaler.transform_logits(arrays["risk_logits"]), axis=1),
            )
        ),
        "alignment": bool(
            np.array_equal(
                np.argsort(arrays["alignment_logits"], axis=1),
                np.argsort(
                    alignment_scaler.transform_logits(arrays["alignment_logits"]), axis=1
                ),
            )
        ),
    }
    operating_point_before = binary_operating_point(
        attack_labels, 1.0 - risk_before[:, 0], frozen_threshold
    )
    operating_point_after = binary_operating_point(
        attack_labels, attack_scores, frozen_threshold
    )
    quality_gates = {
        "ranking_unchanged": all(ranking_unchanged.values()),
        "risk_ece_or_brier_improved": (
            risk_after_metrics["ece"] < risk_before_metrics["ece"]
            or risk_after_metrics["brier"] < risk_before_metrics["brier"]
        ),
        "risk_nll_not_worsened": risk_after_metrics["nll"] <= risk_before_metrics["nll"] + 1e-12,
        "frozen_threshold_fpr_within_target": operating_point_after["fpr"] <= args.target_fpr,
    }
    report = {
        "schema_version": 2,
        "status": "completed",
        "claim_scope": "calibration_split_only_not_final_test_result",
        "provenance": {
            "split": metadata["split"],
            "logits_path": str(args.logits.resolve()),
            "logits_sha256": sha256_file(args.logits),
            "metadata_path": str(metadata_path.resolve()),
            "metadata_sha256": sha256_file(metadata_path),
            "input_path": metadata["input"],
            "input_sha256": metadata["input_sha256"],
            "samples": summary["samples"],
            "authorization_path": str(args.authorization_file.resolve()),
            "authorization_sha256": sha256_file(args.authorization_file),
            "approved_by_project_owner": authorization["approved_by_project_owner"],
        },
        "parameters": {
            "target_fpr": args.target_fpr,
            "n_bins": args.n_bins,
            "classwise_min_samples": args.classwise_min_samples,
        },
        "labels": {
            "risk": list(RISK_LABELS),
            "alignment": metadata["alignment_labels"],
        },
        "temperatures": {
            "risk": risk_scaler.temperature,
            "alignment": alignment_scaler.temperature,
        },
        "ranking_unchanged": ranking_unchanged,
        "quality_gates": {
            **quality_gates,
            "status": "passed" if all(quality_gates.values()) else "failed_engineering_only",
        },
        "risk": {
            "before": risk_before_metrics,
            "after": risk_after_metrics,
            "operating_point_at_frozen_threshold": {
                "before": operating_point_before,
                "after": operating_point_after,
            },
        },
        "alignment": {
            "before": alignment_before_metrics,
            "after": alignment_after_metrics,
        },
        "frozen_attack_threshold": frozen_threshold,
        "threshold_source": "calibration_only",
    }

    calibration.save(args.output)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(report["temperatures"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
