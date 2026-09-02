from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from intentfence.calibration import (
    MultiHeadCalibration,
    calibration_bundle_marker_path,
    load_calibration_protocol_snapshot,
    load_policy_snapshot,
)
from intentfence.constants import LEGACY_ALIGNMENT_LABELS, RISK_LABELS
from intentfence.evaluate import evaluate_dataset
from intentfence.final_test import (
    FINAL_TEST_SPLITS,
    artifact_tree_sha256,
    claim_final_test_ledger,
    complete_final_test_ledger,
    validate_final_test_authorization,
)
from intentfence.inference import BackendPrediction, RuleBackend
from intentfence.metrics import evaluate_risk_predictions
from intentfence.run_manifest import sha256_file


def _final_test_fixture(tmp_path: Path) -> dict:
    model_dir = tmp_path / "model"
    model_dir.mkdir()
    (model_dir / "weights.bin").write_bytes(b"frozen fixture weights")
    calibration_input = tmp_path / "calibration.jsonl"
    calibration_input.write_text(
        "".join(
            json.dumps(sample) + "\n"
            for sample in (
                {
                    "sample_id": "calibration-benign",
                    "source": "synthetic",
                    "untrusted_content": "synthetic calibration benign fixture",
                    "risk_label": "benign",
                    "alignment_label": 0,
                    "template_group": "calibration-benign-group",
                    "split": "calibration",
                    "action_provenance": "missing",
                    "adapter_missing_action": True,
                },
                {
                    "sample_id": "calibration-attack",
                    "source": "synthetic",
                    "untrusted_content": "synthetic calibration attack fixture",
                    "risk_label": "instruction_hijacking",
                    "alignment_label": 1,
                    "template_group": "calibration-attack-group",
                    "split": "calibration",
                    "action_provenance": "missing",
                    "adapter_missing_action": True,
                },
            )
        ),
        encoding="utf-8",
    )
    logits_path = tmp_path / "calibration_logits.npz"
    risk_logits = np.asarray(
        [[4.0, 0.0, -1.0, -2.0, -3.0], [0.0, 4.0, -1.0, -2.0, -3.0]],
        dtype=float,
    )
    alignment_logits = np.asarray([[4.0, 0.0], [0.0, 4.0]], dtype=float)
    risk_labels = np.asarray([0, 1], dtype=int)
    alignment_labels = np.asarray([0, 1], dtype=int)
    np.savez_compressed(
        logits_path,
        risk_logits=risk_logits,
        alignment_logits=alignment_logits,
        risk_labels=risk_labels,
        alignment_labels=alignment_labels,
    )
    metadata_path = logits_path.with_suffix(".json")
    metadata_path.write_text(
        json.dumps(
            {
                "format_version": 3,
                "model_dir": str(model_dir.resolve()),
                "model_artifact_sha256": artifact_tree_sha256(model_dir),
                "model_revision": "fixture-model-revision",
                "input": str(calibration_input.resolve()),
                "input_sha256": sha256_file(calibration_input),
                "logits_sha256": sha256_file(logits_path),
                "split": "calibration",
                "samples": 2,
                "sample_ids": ["calibration-benign", "calibration-attack"],
                "template_groups": ["calibration-benign-group", "calibration-attack-group"],
                "risk_labels": list(RISK_LABELS),
                "risk_logits_shape": [2, 5],
                "alignment_logits_shape": [2, 2],
                "alignment_labels": list(LEGACY_ALIGNMENT_LABELS),
                "input_mode": "context",
                "max_length": 384,
                "alignment_target": "legacy_binary",
            }
        ),
        encoding="utf-8",
    )
    calibration_marker_path = calibration_bundle_marker_path(logits_path)
    calibration_marker_path.write_text(
        json.dumps(
            {
                "format_version": 1,
                "logits_path": str(logits_path.resolve()),
                "metadata_path": str(metadata_path.resolve()),
                "logits_sha256": sha256_file(logits_path),
                "metadata_sha256": sha256_file(metadata_path),
            }
        ),
        encoding="utf-8",
    )
    policy_path = Path(__file__).resolve().parents[1] / "configs" / "policy.yaml"
    policy_snapshot = load_policy_snapshot(policy_path)
    registry_path = Path(__file__).resolve().parents[1] / "configs" / "experiment_registry.yaml"
    protocol_snapshot = load_calibration_protocol_snapshot(registry_path)
    calibration_path = tmp_path / "calibration.json"
    calibration_report_path = tmp_path / "calibration_report.json"
    provenance = {
        "split": "calibration",
        "logits_path": str(logits_path.resolve()),
        "logits_sha256": sha256_file(logits_path),
        "metadata_path": str(metadata_path.resolve()),
        "metadata_sha256": sha256_file(metadata_path),
        "input_path": str(calibration_input.resolve()),
        "input_sha256": sha256_file(calibration_input),
        "samples": 2,
        "model_dir": str(model_dir.resolve()),
        "model_artifact_sha256": artifact_tree_sha256(model_dir),
        "model_revision": "fixture-model-revision",
        "policy_path": policy_snapshot["path"],
        "policy_sha256": policy_snapshot["sha256"],
        "policy_version": policy_snapshot["version"],
        "protocol_registry_path": protocol_snapshot["path"],
        "protocol_registry_sha256": protocol_snapshot["sha256"],
        "protocol_version": protocol_snapshot["protocol_version"],
        "authorization_path": str((tmp_path / "calibration_authorization.json").resolve()),
        "authorization_sha256": "0" * 64,
        "approved_by_project_owner": "fixture-owner",
    }
    calibration_report = {
        "schema_version": 2,
        "status": "completed",
        "claim_scope": "calibration_split_only_not_final_test_result",
        "provenance": provenance,
        "policy": policy_snapshot,
        "protocol": protocol_snapshot,
        "parameters": {
            "target_fpr": 0.01,
            "minimum_viable_attack_tpr": 0.80,
            "n_bins": 15,
            "classwise_min_samples": 10,
        },
        "labels": {
            "risk": list(RISK_LABELS),
            "alignment": list(LEGACY_ALIGNMENT_LABELS),
        },
        "temperatures": {"risk": 1.0, "alignment": 1.0},
        "quality_gates": {
            "ranking_unchanged": True,
            "risk_ece_or_brier_improved": True,
            "risk_nll_not_worsened": True,
            "frozen_threshold_fpr_within_target": True,
            "calibration_tpr_meets_minimum": True,
            "status": "passed",
        },
        "viability": {
            "minimum_viable_attack_tpr": 0.80,
            "calibration_attack_tpr": 1.0,
            "status": "passed",
        },
        "frozen_attack_threshold": 0.5,
        "threshold_source": "calibration_only",
    }
    calibration_path.write_text(
        json.dumps(
            {
                "version": "2",
                "risk": {"temperature": 1.0},
                "alignment": {"temperature": 1.0},
                "metadata": {
                    "format_version": 1,
                    "status": "frozen",
                    "claim_scope": "calibration_split_only_not_final_test_result",
                    "threshold_source": "calibration_only",
                    "frozen_attack_threshold": 0.5,
                    "provenance": provenance,
                    "policy": policy_snapshot,
                    "protocol": protocol_snapshot,
                    "parameters": calibration_report["parameters"],
                    "quality_gates": {"status": "passed"},
                    "labels": {
                        "risk": list(RISK_LABELS),
                        "alignment": list(LEGACY_ALIGNMENT_LABELS),
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    calibration_report_path.write_text(
        json.dumps(calibration_report) + "\n", encoding="utf-8"
    )
    test_inputs = {}
    for split in FINAL_TEST_SPLITS:
        path = tmp_path / f"{split}.jsonl"
        path.write_text(
            json.dumps(
                {
                    "sample_id": f"{split}-sample",
                    "source": "fixture",
                    "untrusted_content": split,
                    "risk_label": "benign",
                    "alignment_label": 0,
                    "template_group": f"{split}-group",
                    "split": split,
                    "action_provenance": "missing",
                    "adapter_missing_action": True,
                }
            )
            + "\n",
            encoding="utf-8",
        )
        test_inputs[split] = path
    authorization_path = tmp_path / "authorization.json"
    payload = {
        "formal_final_test_authorized": True,
        "human_verified": True,
        "final_test_lock_preserved": True,
        "protocol_version": "1.0.0",
        "test_splits": list(FINAL_TEST_SPLITS),
        "frozen_attack_threshold": 0.5,
        "approved_by_project_owner": "fixture-owner",
        "approved_at": "2026-08-31T12:00:00+08:00",
        "model_dir": str(model_dir.resolve()),
        "model_artifact_sha256": artifact_tree_sha256(model_dir),
        "model_revision": "fixture-model-revision",
        "calibration_path": str(calibration_path.resolve()),
        "calibration_sha256": sha256_file(calibration_path),
        "calibration_report_path": str(calibration_report_path.resolve()),
        "calibration_report_sha256": sha256_file(calibration_report_path),
        "policy_path": str(policy_path.resolve()),
        "policy_sha256": policy_snapshot["sha256"],
        "policy_version": policy_snapshot["version"],
        "protocol_registry_path": str(registry_path.resolve()),
        "protocol_registry_sha256": protocol_snapshot["sha256"],
        "test_input_paths": {
            split: str(path.resolve()) for split, path in test_inputs.items()
        },
        "test_input_sha256": {split: sha256_file(path) for split, path in test_inputs.items()},
    }
    authorization_path.write_text(json.dumps(payload), encoding="utf-8")
    return {
        "authorization": authorization_path,
        "registry": registry_path,
        "model": model_dir,
        "calibration": calibration_path,
        "calibration_report": calibration_report_path,
        "policy": policy_path,
        "calibration_logits": logits_path,
        "test_inputs": test_inputs,
    }


def test_final_test_authorization_binds_all_frozen_inputs(tmp_path):
    fixture = _final_test_fixture(tmp_path)
    payload = validate_final_test_authorization(
        fixture["authorization"],
        registry_path=fixture["registry"],
        model_dir=fixture["model"],
        calibration_path=fixture["calibration"],
        calibration_report_path=fixture["calibration_report"],
        policy_path=fixture["policy"],
        test_inputs=fixture["test_inputs"],
        attack_threshold=0.5,
    )

    assert payload["test_splits"] == list(FINAL_TEST_SPLITS)
    mutated_path = fixture["test_inputs"]["test_b"]
    mutated_payload = json.loads(mutated_path.read_text(encoding="utf-8"))
    mutated_payload["untrusted_content"] = "mutated"
    mutated_path.write_text(json.dumps(mutated_payload) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="test_input_sha256"):
        validate_final_test_authorization(
            fixture["authorization"],
            registry_path=fixture["registry"],
            model_dir=fixture["model"],
            calibration_path=fixture["calibration"],
            calibration_report_path=fixture["calibration_report"],
            policy_path=fixture["policy"],
            test_inputs=fixture["test_inputs"],
            attack_threshold=0.5,
        )


def test_final_test_ledger_is_exclusive_and_completes_once(tmp_path):
    fixture = _final_test_fixture(tmp_path)
    ledger_path = tmp_path / "final_test_ledger.json"
    output_dir = tmp_path / "final_results"
    claimed = claim_final_test_ledger(
        ledger_path,
        authorization_path=fixture["authorization"],
        registry_path=fixture["registry"],
        model_dir=fixture["model"],
        calibration_path=fixture["calibration"],
        calibration_report_path=fixture["calibration_report"],
        policy_path=fixture["policy"],
        test_inputs=fixture["test_inputs"],
        attack_threshold=0.5,
        run_id="fixture-run",
        output_dir=output_dir,
    )

    assert claimed["status"] == "claimed"
    with pytest.raises(FileExistsError, match="second formal matrix"):
        claim_final_test_ledger(
            ledger_path,
            authorization_path=fixture["authorization"],
            registry_path=fixture["registry"],
            model_dir=fixture["model"],
            calibration_path=fixture["calibration"],
            calibration_report_path=fixture["calibration_report"],
            policy_path=fixture["policy"],
            test_inputs=fixture["test_inputs"],
            attack_threshold=0.5,
            run_id="another-run",
            output_dir=tmp_path / "another-results",
        )

    result_paths = {}
    for split in FINAL_TEST_SPLITS:
        result_dir = output_dir / split
        result_dir.mkdir(parents=True)
        (result_dir / "metrics.json").write_text("{}\n", encoding="utf-8")
        result_paths[split] = result_dir
    with pytest.raises(ValueError, match="predictions.jsonl and metrics.json"):
        complete_final_test_ledger(
            ledger_path,
            run_id="fixture-run",
            result_paths=result_paths,
        )

    calibration_sha256 = sha256_file(fixture["calibration"])
    for split, result_dir in result_paths.items():
        prediction = {
            "sample_id": f"{split}-sample",
            "split": split,
            "template_group": f"{split}-group",
            "backend": "fixture-backend",
            "revision": "fixture-model-revision",
            "true_risk": "benign",
            "predicted_risk": "benign",
            "risk_probabilities": {
                label: (1.0 if label == "benign" else 0.0) for label in RISK_LABELS
            },
            "attack_score": 0.0,
            "attack_threshold": 0.5,
            "threshold_source": "calibration_only",
            "calibrated": True,
            "calibration_version": "2",
            "calibration_sha256": calibration_sha256,
        }
        (result_dir / "predictions.jsonl").write_text(
            json.dumps(prediction) + "\n", encoding="utf-8"
        )
        (result_dir / "metrics.json").write_text(
            json.dumps(
                {
                    "threshold_source": "calibration_only",
                    "operating_point": {"threshold": 0.5},
                }
            )
            + "\n",
            encoding="utf-8",
        )
    with pytest.raises(ValueError, match="metrics do not match predictions"):
        complete_final_test_ledger(
            ledger_path,
            run_id="fixture-run",
            result_paths=result_paths,
        )
    expected_metrics = evaluate_risk_predictions(
        [0],
        [[1.0, 0.0, 0.0, 0.0, 0.0]],
        attack_threshold=0.5,
    )
    for result_dir in result_paths.values():
        (result_dir / "metrics.json").write_text(
            json.dumps(expected_metrics) + "\n", encoding="utf-8"
        )
    completed = complete_final_test_ledger(
        ledger_path,
        run_id="fixture-run",
        result_paths=result_paths,
    )

    assert completed["status"] == "completed"
    with pytest.raises(ValueError, match="claimed run"):
        complete_final_test_ledger(
            ledger_path,
            run_id="fixture-run",
            result_paths=result_paths,
        )


def test_evaluate_dataset_uses_matrix_root_and_split_result_directory(tmp_path):
    fixture = _final_test_fixture(tmp_path)
    ledger_path = tmp_path / "final_test_ledger.json"
    output_root = tmp_path / "final_results"
    claim_final_test_ledger(
        ledger_path,
        authorization_path=fixture["authorization"],
        registry_path=fixture["registry"],
        model_dir=fixture["model"],
        calibration_path=fixture["calibration"],
        calibration_report_path=fixture["calibration_report"],
        policy_path=fixture["policy"],
        test_inputs=fixture["test_inputs"],
        attack_threshold=0.5,
        run_id="fixture-evaluation-run",
        output_dir=output_root,
    )

    with pytest.raises(ValueError, match="calibrated backend"):
        evaluate_dataset(
            RuleBackend(),
            fixture["test_inputs"]["test_a"],
            output_root / "test_a",
            attack_threshold=0.5,
            final_test_ledger=ledger_path,
        )

    class FixtureCalibratedBackend:
        name = "fixture-calibrated"
        model_revision = "fixture-model-revision"

        def __init__(self) -> None:
            self.calibration_path = fixture["calibration"].resolve()
            self.calibration = MultiHeadCalibration.load(self.calibration_path)

        def predict(self, user_goal: str, untrusted_content: str, proposed_action: str):
            del user_goal, untrusted_content, proposed_action
            probabilities = {label: (1.0 if label == "benign" else 0.0) for label in RISK_LABELS}
            return BackendPrediction(
                probabilities=probabilities,
                alignment_conflict_probability=0.0,
                predicted_risk="benign",
                attack_score=0.0,
                backend=self.name,
                calibrated=True,
            )

    metrics = evaluate_dataset(
        FixtureCalibratedBackend(),
        fixture["test_inputs"]["test_a"],
        output_root / "test_a",
        attack_threshold=0.5,
        final_test_ledger=ledger_path,
    )

    assert metrics["threshold_source"] == "calibration_only"
    assert (output_root / "test_a" / "predictions.jsonl").is_file()


def test_final_test_rejects_incomplete_quality_gate_set(tmp_path):
    fixture = _final_test_fixture(tmp_path)
    report = json.loads(fixture["calibration_report"].read_text(encoding="utf-8"))
    report["quality_gates"].pop("risk_nll_not_worsened")
    fixture["calibration_report"].write_text(json.dumps(report), encoding="utf-8")
    authorization_path = _authorization_copy_with_report_hash(
        fixture, tmp_path / "incomplete-gates-authorization.json"
    )

    with pytest.raises(ValueError, match="quality gate set"):
        validate_final_test_authorization(
            authorization_path,
            registry_path=fixture["registry"],
            model_dir=fixture["model"],
            calibration_path=fixture["calibration"],
            calibration_report_path=fixture["calibration_report"],
            policy_path=fixture["policy"],
            test_inputs=fixture["test_inputs"],
            attack_threshold=0.5,
        )


def _authorization_copy_with_report_hash(fixture: dict, destination: Path) -> Path:
    payload = json.loads(fixture["authorization"].read_text(encoding="utf-8"))
    payload["calibration_report_sha256"] = sha256_file(fixture["calibration_report"])
    destination.write_text(json.dumps(payload), encoding="utf-8")
    return destination


def test_final_test_rejects_policy_revision_drift(tmp_path):
    fixture = _final_test_fixture(tmp_path)
    authorization = json.loads(fixture["authorization"].read_text(encoding="utf-8"))
    authorization["policy_version"] = "drifted-policy"
    authorization_path = tmp_path / "drifted-authorization.json"
    authorization_path.write_text(json.dumps(authorization), encoding="utf-8")

    with pytest.raises(ValueError, match="policy_version"):
        validate_final_test_authorization(
            authorization_path,
            registry_path=fixture["registry"],
            model_dir=fixture["model"],
            calibration_path=fixture["calibration"],
            calibration_report_path=fixture["calibration_report"],
            policy_path=fixture["policy"],
            test_inputs=fixture["test_inputs"],
            attack_threshold=0.5,
        )


def test_final_test_rejects_report_quality_gate_drift(tmp_path):
    fixture = _final_test_fixture(tmp_path)
    report = json.loads(fixture["calibration_report"].read_text(encoding="utf-8"))
    report["quality_gates"]["risk_nll_not_worsened"] = False
    fixture["calibration_report"].write_text(json.dumps(report), encoding="utf-8")
    authorization_path = _authorization_copy_with_report_hash(
        fixture, tmp_path / "report-drift-authorization.json"
    )

    with pytest.raises(ValueError, match="quality gate"):
        validate_final_test_authorization(
            authorization_path,
            registry_path=fixture["registry"],
            model_dir=fixture["model"],
            calibration_path=fixture["calibration"],
            calibration_report_path=fixture["calibration_report"],
            policy_path=fixture["policy"],
            test_inputs=fixture["test_inputs"],
            attack_threshold=0.5,
        )


def test_final_test_rejects_calibration_artifact_report_mismatch(tmp_path):
    fixture = _final_test_fixture(tmp_path)
    calibration = json.loads(fixture["calibration"].read_text(encoding="utf-8"))
    calibration["metadata"]["parameters"]["target_fpr"] = 0.02
    fixture["calibration"].write_text(json.dumps(calibration), encoding="utf-8")
    authorization = json.loads(fixture["authorization"].read_text(encoding="utf-8"))
    authorization["calibration_sha256"] = sha256_file(fixture["calibration"])
    authorization_path = tmp_path / "calibration-drift-authorization.json"
    authorization_path.write_text(json.dumps(authorization), encoding="utf-8")

    with pytest.raises(ValueError, match="parameters"):
        validate_final_test_authorization(
            authorization_path,
            registry_path=fixture["registry"],
            model_dir=fixture["model"],
            calibration_path=fixture["calibration"],
            calibration_report_path=fixture["calibration_report"],
            policy_path=fixture["policy"],
            test_inputs=fixture["test_inputs"],
            attack_threshold=0.5,
        )
