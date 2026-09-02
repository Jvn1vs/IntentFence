from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from intentfence.constants import RISK_TO_ID
from intentfence.evaluation import TEST_SPLITS, content_length_bucket
from intentfence.inference import RuleBackend, TorchBackend
from intentfence.metrics import evaluate_risk_predictions
from intentfence.run_manifest import artifact_tree_sha256, sha256_file
from intentfence.schema import read_jsonl


def _validate_claimed_final_test_ledger(
    ledger_path: str | Path,
    *,
    split: str,
    input_path: Path,
    output_dir: Path,
    attack_threshold: float,
) -> dict:
    from intentfence.final_test import FINAL_TEST_SPLITS, validate_final_test_authorization

    source = Path(ledger_path)
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"final-test ledger must be valid JSON: {source}") from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise ValueError("final-test ledger schema is invalid")
    if payload.get("status") != "claimed":
        raise ValueError("final-test evaluation requires a claimed ledger")
    if payload.get("test_splits") != list(FINAL_TEST_SPLITS):
        raise ValueError("final-test ledger test_splits are invalid")
    if split not in FINAL_TEST_SPLITS:
        raise ValueError(f"final-test ledger does not support split={split}")
    output_value = payload.get("output_dir")
    if not isinstance(output_value, str) or not Path(output_value).is_absolute():
        raise ValueError("final-test ledger output_dir is invalid")
    expected_output = Path(output_value) / split
    if expected_output.resolve() != output_dir.resolve():
        raise ValueError("final-test ledger output_dir does not match evaluation output")
    try:
        ledger_threshold = float(payload["attack_threshold"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("final-test ledger attack threshold is invalid") from exc
    if not np.isclose(ledger_threshold, attack_threshold, atol=1e-15, rtol=0.0):
        raise ValueError("final-test ledger attack threshold does not match evaluation")
    required_fields = (
        "authorization_path",
        "authorization_sha256",
        "protocol_registry_path",
        "protocol_registry_sha256",
        "model_dir",
        "model_artifact_sha256",
        "model_revision",
        "calibration_path",
        "calibration_sha256",
        "calibration_version",
        "calibration_report_path",
        "calibration_report_sha256",
        "policy_path",
        "policy_sha256",
        "policy_version",
        "test_input_paths",
        "test_input_sha256",
    )
    if any(field not in payload for field in required_fields):
        raise ValueError("final-test ledger is missing complete authorization bindings")
    recorded_paths = payload["test_input_paths"]
    recorded_hashes = payload["test_input_sha256"]
    if not isinstance(recorded_paths, dict) or not isinstance(recorded_hashes, dict):
        raise ValueError("final-test ledger input bindings are missing")
    if set(recorded_paths) != set(FINAL_TEST_SPLITS) or set(recorded_hashes) != set(FINAL_TEST_SPLITS):
        raise ValueError("final-test ledger input bindings are incomplete")
    recorded_path = recorded_paths.get(split)
    if recorded_path != str(input_path.resolve()):
        raise ValueError("final-test ledger input path does not match evaluation")
    recorded_hash = recorded_hashes.get(split)
    if recorded_hash != sha256_file(input_path):
        raise ValueError("final-test ledger input hash does not match evaluation")

    try:
        registry_path = Path(payload["protocol_registry_path"])
        model_dir = Path(payload["model_dir"])
        calibration_path = Path(payload["calibration_path"])
        calibration_report_path = Path(payload["calibration_report_path"])
        policy_path = Path(payload["policy_path"])
        test_inputs = {split_name: Path(path) for split_name, path in recorded_paths.items()}
        authorization = validate_final_test_authorization(
            payload["authorization_path"],
            registry_path=registry_path,
            model_dir=model_dir,
            calibration_path=calibration_path,
            calibration_report_path=calibration_report_path,
            policy_path=policy_path,
            test_inputs=test_inputs,
            attack_threshold=attack_threshold,
        )
    except (FileNotFoundError, OSError, TypeError, ValueError) as exc:
        raise ValueError(
            "final-test evaluation requires a complete owner-authorized claimed ledger"
        ) from exc
    expected_bindings = {
        "protocol_version": authorization["protocol_version"],
        "protocol_registry_path": str(registry_path.resolve()),
        "protocol_registry_sha256": sha256_file(registry_path),
        "authorization_path": str(Path(payload["authorization_path"]).resolve()),
        "authorization_sha256": sha256_file(payload["authorization_path"]),
        "model_dir": str(model_dir.resolve()),
        "model_artifact_sha256": artifact_tree_sha256(model_dir),
        "model_revision": authorization.get("model_revision"),
        "calibration_path": str(calibration_path.resolve()),
        "calibration_sha256": sha256_file(calibration_path),
        "calibration_version": "2",
        "calibration_report_path": str(calibration_report_path.resolve()),
        "calibration_report_sha256": sha256_file(calibration_report_path),
        "policy_path": str(policy_path.resolve()),
        "policy_sha256": sha256_file(policy_path),
        "policy_version": authorization.get("policy_version"),
    }
    for field, expected in expected_bindings.items():
        if payload.get(field) != expected:
            raise ValueError(f"final-test ledger binding drifted: {field}")
    expected_hashes = {split_name: sha256_file(path) for split_name, path in test_inputs.items()}
    if recorded_hashes != expected_hashes:
        raise ValueError("final-test ledger test input hashes do not match the run")
    return payload


def evaluate_dataset(
    backend: RuleBackend | TorchBackend,
    input_path: Path,
    output_dir: Path,
    *,
    attack_threshold: float | None = None,
    final_test_ledger: str | Path | None = None,
) -> dict:
    samples = read_jsonl(input_path)
    if not samples:
        raise ValueError(f"Evaluation input is empty: {input_path}")
    split = samples[0].split or "unspecified"
    if any((sample.split or "unspecified") != split for sample in samples):
        raise ValueError("Evaluation input mixes split values")
    if split in TEST_SPLITS and attack_threshold is None:
        raise ValueError(
            "Test evaluation requires an explicit calibration-derived --attack-threshold"
        )
    claimed_ledger = None
    if split in TEST_SPLITS:
        if final_test_ledger is None:
            raise ValueError(
                "formal final-test evaluation requires a claimed ledger; use run_final_matrix.py"
            )
        claimed_ledger = _validate_claimed_final_test_ledger(
            final_test_ledger,
            split=split,
            input_path=input_path,
            output_dir=output_dir,
            attack_threshold=float(attack_threshold),
        )
        backend_calibration_path = getattr(backend, "calibration_path", None)
        backend_calibration = getattr(backend, "calibration", None)
        if backend_calibration_path is None or backend_calibration is None:
            raise ValueError(
                "formal final-test evaluation requires the ledger-bound calibrated backend"
            )
        if Path(backend_calibration_path).resolve() != Path(
            claimed_ledger["calibration_path"]
        ).resolve():
            raise ValueError("backend calibration path does not match the final-test ledger")
        if sha256_file(backend_calibration_path) != claimed_ledger["calibration_sha256"]:
            raise ValueError("backend calibration hash does not match the final-test ledger")
        if getattr(backend_calibration, "version", None) != claimed_ledger["calibration_version"]:
            raise ValueError("backend calibration version does not match the final-test ledger")
        if getattr(backend, "model_revision", None) != claimed_ledger["model_revision"]:
            raise ValueError("backend model revision does not match the final-test ledger")
        calibration_metadata = getattr(backend_calibration, "metadata", None)
        calibration_provenance = (
            calibration_metadata.get("provenance")
            if isinstance(calibration_metadata, dict)
            else None
        )
        if not isinstance(calibration_provenance, dict) or calibration_provenance.get(
            "model_dir"
        ) != claimed_ledger["model_dir"]:
            raise ValueError("backend model directory does not match the final-test ledger")
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"Refusing to overwrite non-empty evaluation directory: {output_dir}")
    backend_revision = getattr(getattr(backend, "metadata", None), "model_revision", None)
    backend_revision = backend_revision or getattr(backend, "name", "unknown")
    calibration_path = getattr(backend, "calibration_path", None)
    calibration = getattr(backend, "calibration", None)
    if split in TEST_SPLITS and attack_threshold is not None and calibration is not None:
        calibration_metadata = getattr(calibration, "metadata", None)
        if not isinstance(calibration_metadata, dict):
            raise ValueError("test evaluation requires a frozen calibration metadata binding")
        try:
            frozen_threshold = float(calibration_metadata["frozen_attack_threshold"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("test evaluation calibration threshold is missing") from exc
        if not np.isclose(frozen_threshold, attack_threshold, atol=1e-15, rtol=0.0):
            raise ValueError(
                "test evaluation attack_threshold does not match the frozen calibration artifact"
            )
    calibration_sha256 = (
        sha256_file(calibration_path)
        if calibration_path is not None and Path(calibration_path).is_file()
        else None
    )
    threshold_source = (
        "calibration_only" if attack_threshold is not None else "dataset_empirical"
    )
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
                "split": split,
                "template_group": sample.template_group,
                "scenario": sample.scenario,
                "attack_family": sample.attack_family,
                "content_length": len(sample.untrusted_content),
                "content_length_bucket": content_length_bucket(len(sample.untrusted_content)),
                "revision": backend_revision,
                "true_risk": sample.risk_label,
                "predicted_risk": prediction.predicted_risk,
                "attack_score": prediction.attack_score,
                "alignment_conflict_probability": prediction.alignment_conflict_probability,
                "risk_probabilities": prediction.probabilities,
                "backend": prediction.backend,
                "calibrated": prediction.calibrated,
                "attack_threshold": (
                    float(attack_threshold) if attack_threshold is not None else None
                ),
                "threshold_source": threshold_source,
                "calibration_version": getattr(
                    getattr(backend, "calibration", None), "version", None
                ),
                "calibration_sha256": calibration_sha256,
            }
        )
    metrics = evaluate_risk_predictions(
        np.array(labels), np.array(probabilities), attack_threshold=attack_threshold
    )
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
    parser.add_argument(
        "--attack-threshold",
        type=float,
        help="frozen threshold selected on calibration; required for test splits",
    )
    args = parser.parse_args()
    try:
        probe_samples = read_jsonl(args.input)
    except (OSError, ValueError) as exc:
        raise SystemExit(f"evaluation input preflight failed: {exc}") from exc
    probe_split = probe_samples[0].split if probe_samples else None
    if probe_split in TEST_SPLITS:
        raise SystemExit(
            "direct evaluation of formal test splits is disabled; use scripts/run_final_matrix.py"
        )
    if args.backend == "torch":
        if args.model_dir is None:
            parser.error("--model-dir is required for --backend torch")
        backend = TorchBackend(args.model_dir, args.calibration)
    else:
        backend = RuleBackend()
    print(
        json.dumps(
            evaluate_dataset(
                backend,
                args.input,
                args.output_dir,
                attack_threshold=args.attack_threshold,
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
