from __future__ import annotations

import argparse
import json
from pathlib import Path

from intentfence.evaluate import evaluate_dataset
from intentfence.final_test import (
    FINAL_TEST_SPLITS,
    claim_final_test_ledger,
    complete_final_test_ledger,
    validate_final_test_authorization,
)
from intentfence.inference import TorchBackend


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the one authorized Test A/B/C matrix at a frozen threshold"
    )
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--calibration", type=Path, required=True)
    parser.add_argument("--calibration-report", type=Path, required=True)
    parser.add_argument("--test-a", type=Path, required=True)
    parser.add_argument("--test-b", type=Path, required=True)
    parser.add_argument("--test-c", type=Path, required=True)
    parser.add_argument("--attack-threshold", type=float, required=True)
    parser.add_argument("--authorization-file", type=Path, required=True)
    parser.add_argument("--ledger-file", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--protocol-registry", type=Path, default=Path("configs/experiment_registry.yaml"))
    parser.add_argument("--device", default="cpu")
    parser.add_argument(
        "--preflight-only",
        action="store_true",
        help="validate authorization, hashes, paths and lock state without model inference",
    )
    args = parser.parse_args()
    test_inputs = {
        "test_a": args.test_a,
        "test_b": args.test_b,
        "test_c": args.test_c,
    }
    if args.output_dir.exists():
        raise SystemExit(f"refusing to overwrite final-test output directory: {args.output_dir}")
    if args.ledger_file.exists():
        raise SystemExit(f"refusing a second final-test matrix; ledger exists: {args.ledger_file}")
    try:
        authorization = validate_final_test_authorization(
            args.authorization_file,
            registry_path=args.protocol_registry,
            model_dir=args.model_dir,
            calibration_path=args.calibration,
            calibration_report_path=args.calibration_report,
            test_inputs=test_inputs,
            attack_threshold=args.attack_threshold,
        )
    except (FileNotFoundError, OSError, ValueError) as exc:
        raise SystemExit(f"final-test preflight failed: {exc}") from exc

    if args.preflight_only:
        print(
            json.dumps(
                {
                    "status": "preflight_passed",
                    "protocol_version": authorization["protocol_version"],
                    "test_splits": list(FINAL_TEST_SPLITS),
                    "attack_threshold": args.attack_threshold,
                    "model_dir": str(args.model_dir.resolve()),
                },
                indent=2,
                sort_keys=True,
            )
        )
        return

    claim_final_test_ledger(
        args.ledger_file,
        authorization_path=args.authorization_file,
        registry_path=args.protocol_registry,
        model_dir=args.model_dir,
        calibration_path=args.calibration,
        calibration_report_path=args.calibration_report,
        test_inputs=test_inputs,
        attack_threshold=args.attack_threshold,
        run_id=args.run_id,
        output_dir=args.output_dir,
    )
    backend = TorchBackend(args.model_dir, args.calibration, device=args.device)
    result_paths: dict[str, Path] = {}
    for split, input_path in test_inputs.items():
        result_dir = args.output_dir / split
        evaluate_dataset(
            backend,
            input_path,
            result_dir,
            attack_threshold=args.attack_threshold,
        )
        result_paths[split] = result_dir
    completed = complete_final_test_ledger(
        args.ledger_file,
        run_id=args.run_id,
        result_paths=result_paths,
    )
    print(
        json.dumps(
            {
                "status": completed["status"],
                "run_id": completed["run_id"],
                "test_splits": completed["test_splits"],
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
