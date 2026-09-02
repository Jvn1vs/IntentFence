from __future__ import annotations

import json
import math
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from intentfence.calibration import (
    load_calibration_arrays,
    load_calibration_protocol_snapshot,
    load_policy_snapshot,
    validate_frozen_calibration_metadata,
)
from intentfence.constants import RISK_LABELS
from intentfence.evaluation import load_prediction_jsonl
from intentfence.metrics import evaluate_risk_predictions
from intentfence.run_manifest import artifact_tree_sha256, sha256_file
from intentfence.schema import read_jsonl

FINAL_TEST_SPLITS = ("test_a", "test_b", "test_c")
C2C_QUALITY_GATE_FIELDS = frozenset(
    {
        "ranking_unchanged",
        "risk_ece_or_brier_improved",
        "risk_nll_not_worsened",
        "frozen_threshold_fpr_within_target",
        "calibration_tpr_meets_minimum",
    }
)


def _has_timezone(value: Any) -> bool:
    if not isinstance(value, str) or not value:
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None


def _read_object(path: Path, *, description: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"{description} must be valid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{description} must be a JSON object: {path}")
    return payload


def _validate_c2c_binding(
    *,
    calibration_path: Path,
    calibration_report_path: Path,
    model_dir: Path,
    policy_path: Path,
    registry_path: Path,
    attack_threshold: float,
    registry: dict[str, Any],
) -> dict[str, Any]:
    """Require a semantically bound, quality-gated C2c artifact before C3a."""

    report = _read_object(calibration_report_path, description="calibration report")
    if report.get("schema_version") != 2 or report.get("status") != "completed":
        raise ValueError("calibration report is not a completed C2c report")
    if report.get("claim_scope") != "calibration_split_only_not_final_test_result":
        raise ValueError("calibration report claim scope is invalid")
    if report.get("threshold_source") != "calibration_only":
        raise ValueError("calibration report threshold_source must be calibration_only")

    calibration_contract = registry.get("calibration")
    if not isinstance(calibration_contract, dict):
        raise ValueError("frozen registry calibration contract is missing")
    protocol_snapshot = load_calibration_protocol_snapshot(registry_path)
    expected_target_fpr = protocol_snapshot["benign_fpr_ceiling"]
    parameters = report.get("parameters")
    if not isinstance(parameters, dict):
        raise ValueError("calibration report parameters are missing")
    try:
        report_target_fpr = float(parameters["target_fpr"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("calibration report target_fpr is invalid") from exc
    if not math.isclose(report_target_fpr, expected_target_fpr, rel_tol=0.0, abs_tol=1e-15):
        raise ValueError("calibration report target_fpr does not match the frozen registry")
    if calibration_contract.get("split") != "calibration":
        raise ValueError("frozen registry calibration split is invalid")
    if calibration_contract.get("method") != "temperature_scaling_per_head":
        raise ValueError("frozen registry calibration method is invalid")
    if calibration_contract.get("threshold_source") != "calibration_only":
        raise ValueError("frozen registry calibration threshold source is invalid")
    if report.get("protocol") != protocol_snapshot:
        raise ValueError("calibration report protocol snapshot does not match the frozen registry")

    quality_gates = report.get("quality_gates")
    if not isinstance(quality_gates, dict) or quality_gates.get("status") != "passed":
        raise ValueError("calibration report quality gates did not pass")
    if set(quality_gates) - {"status"} != C2C_QUALITY_GATE_FIELDS:
        raise ValueError("calibration report quality gate set is incomplete or unexpected")
    gate_values = [value for key, value in quality_gates.items() if key != "status"]
    if not gate_values or not all(value is True for value in gate_values):
        raise ValueError("calibration report contains a failed quality gate")
    viability = report.get("viability")
    if not isinstance(viability, dict) or viability.get("status") != "passed":
        raise ValueError("calibration report viability gate did not pass")
    try:
        expected_minimum_tpr = protocol_snapshot["minimum_viable_attack_tpr"]
        report_minimum_tpr = float(parameters["minimum_viable_attack_tpr"])
        viability_minimum_tpr = float(viability["minimum_viable_attack_tpr"])
        calibration_tpr = float(viability["calibration_attack_tpr"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("calibration report viability fields are invalid") from exc
    if not all(
        math.isfinite(value)
        for value in (
            expected_minimum_tpr,
            report_minimum_tpr,
            viability_minimum_tpr,
            calibration_tpr,
        )
    ):
        raise ValueError("calibration report viability fields must be finite")
    if not all(
        math.isclose(value, expected_minimum_tpr, rel_tol=0.0, abs_tol=1e-15)
        for value in (report_minimum_tpr, viability_minimum_tpr)
    ):
        raise ValueError("calibration report minimum viable TPR does not match the frozen registry")
    if calibration_tpr < expected_minimum_tpr:
        raise ValueError("calibration report TPR is below the frozen minimum")
    if not math.isclose(
        float(report.get("frozen_attack_threshold", math.nan)),
        attack_threshold,
        rel_tol=0.0,
        abs_tol=1e-15,
    ):
        raise ValueError("calibration report threshold does not match the run")

    policy_snapshot = load_policy_snapshot(policy_path)
    if report.get("policy") != policy_snapshot:
        raise ValueError("calibration report policy snapshot does not match the frozen policy")
    provenance = report.get("provenance")
    if not isinstance(provenance, dict) or provenance.get("split") != "calibration":
        raise ValueError("calibration report provenance is not bound to calibration")
    expected_policy_path = str(policy_path.resolve())
    if provenance.get("policy_path") != expected_policy_path:
        raise ValueError("calibration report policy path does not match the run")
    if provenance.get("policy_sha256") != policy_snapshot["sha256"]:
        raise ValueError("calibration report policy hash does not match the run")
    if provenance.get("policy_version") != policy_snapshot["version"]:
        raise ValueError("calibration report policy version does not match the run")
    expected_registry_path = str(registry_path.resolve())
    if provenance.get("protocol_registry_path") != expected_registry_path:
        raise ValueError("calibration report protocol registry path does not match the run")
    if provenance.get("protocol_registry_sha256") != protocol_snapshot["sha256"]:
        raise ValueError("calibration report protocol registry hash does not match the run")
    if provenance.get("protocol_version") != protocol_snapshot["protocol_version"]:
        raise ValueError("calibration report protocol version does not match the run")

    logits_value = provenance.get("logits_path")
    metadata_value = provenance.get("metadata_path")
    if not isinstance(logits_value, str) or not isinstance(metadata_value, str):
        raise ValueError("calibration report logits provenance is incomplete")
    logits_path = Path(logits_value)
    metadata_path = Path(metadata_value)
    arrays, metadata = load_calibration_arrays(logits_path, metadata_path)
    del arrays
    expected_model_dir = str(model_dir.resolve())
    if provenance.get("model_dir") != expected_model_dir:
        raise ValueError("calibration report model directory does not match the final-test run")
    if provenance.get("model_artifact_sha256") != artifact_tree_sha256(model_dir):
        raise ValueError("calibration report model artifact hash does not match the final-test run")
    expected_provenance = {
        "split": metadata["split"],
        "logits_path": str(logits_path.resolve()),
        "logits_sha256": sha256_file(logits_path),
        "metadata_path": str(metadata_path.resolve()),
        "metadata_sha256": sha256_file(metadata_path),
        "input_path": metadata["input"],
        "input_sha256": metadata["input_sha256"],
        "samples": metadata["samples"],
        "model_dir": metadata["model_dir"],
        "model_artifact_sha256": metadata["model_artifact_sha256"],
        "model_revision": metadata["model_revision"],
        "policy_path": policy_snapshot["path"],
        "policy_sha256": policy_snapshot["sha256"],
        "policy_version": policy_snapshot["version"],
        "protocol_registry_path": protocol_snapshot["path"],
        "protocol_registry_sha256": protocol_snapshot["sha256"],
        "protocol_version": protocol_snapshot["protocol_version"],
    }
    for field, expected in expected_provenance.items():
        if provenance.get(field) != expected:
            raise ValueError(f"calibration report provenance field is not bound: {field}")

    calibration_payload = _read_object(calibration_path, description="calibration artifact")
    if calibration_payload.get("version") != "2":
        raise ValueError("calibration artifact version is not C2c version 2")
    artifact_metadata = calibration_payload.get("metadata")
    if not isinstance(artifact_metadata, dict):
        raise ValueError("calibration artifact metadata is missing")
    validate_frozen_calibration_metadata(artifact_metadata)
    if artifact_metadata.get("claim_scope") != report.get("claim_scope"):
        raise ValueError("calibration artifact claim scope does not match the report")
    if artifact_metadata.get("provenance") != provenance:
        raise ValueError("calibration artifact provenance does not match the report")
    if artifact_metadata.get("policy") != policy_snapshot:
        raise ValueError("calibration artifact policy does not match the frozen policy")
    if artifact_metadata.get("protocol") != protocol_snapshot:
        raise ValueError("calibration artifact protocol does not match the frozen registry")
    if artifact_metadata.get("quality_gates") != {"status": "passed"}:
        raise ValueError("calibration artifact quality gate is invalid")
    if artifact_metadata.get("parameters") != parameters:
        raise ValueError("calibration artifact parameters do not match the report")
    if artifact_metadata.get("labels") != report.get("labels"):
        raise ValueError("calibration artifact labels do not match the report")
    if not math.isclose(
        float(artifact_metadata.get("frozen_attack_threshold", math.nan)),
        attack_threshold,
        rel_tol=0.0,
        abs_tol=1e-15,
    ):
        raise ValueError("calibration artifact threshold does not match the run")
    temperatures = report.get("temperatures")
    if not isinstance(temperatures, dict):
        raise ValueError("calibration report temperatures are missing")
    for head in ("risk", "alignment"):
        try:
            report_temperature = float(temperatures[head])
            artifact_temperature = float(calibration_payload[head]["temperature"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"calibration temperature is missing for {head}") from exc
        if not math.isclose(report_temperature, artifact_temperature, rel_tol=0.0, abs_tol=1e-15):
            raise ValueError(f"calibration artifact temperature does not match report: {head}")
    return report


def validate_final_test_authorization(
    authorization_path: str | Path,
    *,
    registry_path: str | Path,
    model_dir: str | Path,
    calibration_path: str | Path,
    calibration_report_path: str | Path,
    policy_path: str | Path,
    test_inputs: dict[str, str | Path],
    attack_threshold: float,
) -> dict[str, Any]:
    """Validate a project-owner authorization for one immutable Test A/B/C matrix."""

    authorization_path = Path(authorization_path)
    registry_path = Path(registry_path)
    model_dir = Path(model_dir)
    calibration_path = Path(calibration_path)
    calibration_report_path = Path(calibration_report_path)
    policy_path = Path(policy_path)
    if not math.isfinite(attack_threshold) or not 0 <= attack_threshold <= 1:
        raise ValueError("attack_threshold must be a finite value in [0, 1]")
    registry = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
    if not isinstance(registry, dict) or registry.get("status") != "frozen":
        raise ValueError("final-test authorization requires a frozen experiment registry")
    protocol_version = str(registry.get("protocol_version", ""))
    test_lock = registry.get("test_lock", {})
    if test_lock.get("enabled") is not True or test_lock.get("formal_test_runs_per_protocol") != 1:
        raise ValueError("frozen registry must enforce exactly one formal test run")

    payload = _read_object(authorization_path, description="final-test authorization")
    if payload.get("formal_final_test_authorized") is not True:
        raise ValueError("authorization requires formal_final_test_authorized=true")
    if payload.get("human_verified") is not True:
        raise ValueError("authorization requires independent human_verified=true")
    if payload.get("final_test_lock_preserved") is not True:
        raise ValueError("authorization must preserve the final-test lock")
    if payload.get("protocol_version") != protocol_version:
        raise ValueError("authorization protocol_version does not match the frozen registry")
    if payload.get("protocol_registry_path") != str(registry_path.resolve()):
        raise ValueError("authorization protocol registry path does not match the run")
    if payload.get("protocol_registry_sha256") != sha256_file(registry_path):
        raise ValueError("authorization protocol registry hash does not match the run")
    if not isinstance(payload.get("approved_by_project_owner"), str) or not payload[
        "approved_by_project_owner"
    ].strip():
        raise ValueError("authorization requires approved_by_project_owner")
    if not _has_timezone(payload.get("approved_at")):
        raise ValueError("authorization approved_at must include a timezone")

    expected_splits = list(FINAL_TEST_SPLITS)
    if payload.get("test_splits") != expected_splits:
        raise ValueError(f"authorization test_splits must be exactly {expected_splits}")
    if not math.isclose(
        float(payload.get("frozen_attack_threshold", math.nan)),
        attack_threshold,
        rel_tol=0.0,
        abs_tol=1e-15,
    ):
        raise ValueError("authorization frozen_attack_threshold does not match the run")
    if payload.get("model_dir") != str(model_dir.resolve()):
        raise ValueError("authorization model_dir does not match the run")
    if payload.get("model_artifact_sha256") != artifact_tree_sha256(model_dir):
        raise ValueError("authorization model_artifact_sha256 does not match the model directory")
    if payload.get("calibration_path") != str(calibration_path.resolve()):
        raise ValueError("authorization calibration_path does not match the run")
    if payload.get("calibration_sha256") != sha256_file(calibration_path):
        raise ValueError("authorization calibration_sha256 does not match the calibration file")
    if payload.get("calibration_report_path") != str(calibration_report_path.resolve()):
        raise ValueError("authorization calibration_report_path does not match the run")
    if payload.get("calibration_report_sha256") != sha256_file(calibration_report_path):
        raise ValueError("authorization calibration_report_sha256 does not match the report")
    if payload.get("policy_path") != str(policy_path.resolve()):
        raise ValueError("authorization policy_path does not match the run")
    policy_snapshot = load_policy_snapshot(policy_path)
    if payload.get("policy_sha256") != policy_snapshot["sha256"]:
        raise ValueError("authorization policy_sha256 does not match the run")
    if payload.get("policy_version") != policy_snapshot["version"]:
        raise ValueError("authorization policy_version does not match the run")
    calibration_report = _validate_c2c_binding(
        calibration_path=calibration_path,
        calibration_report_path=calibration_report_path,
        model_dir=model_dir,
        policy_path=policy_path,
        registry_path=registry_path,
        attack_threshold=attack_threshold,
        registry=registry,
    )
    calibration_provenance = calibration_report["provenance"]
    if payload.get("model_revision") != calibration_provenance["model_revision"]:
        raise ValueError("authorization model_revision does not match the frozen calibration model")

    recorded_paths = payload.get("test_input_paths")
    recorded_hashes = payload.get("test_input_sha256")
    expected_paths = {split: str(Path(path).resolve()) for split, path in test_inputs.items()}
    expected_hashes = {split: sha256_file(path) for split, path in test_inputs.items()}
    if set(expected_paths) != set(FINAL_TEST_SPLITS):
        raise ValueError(f"test_inputs must contain exactly {list(FINAL_TEST_SPLITS)}")
    sample_ids: set[str] = set()
    template_groups: set[str] = set()
    calibration_input = Path(calibration_report["provenance"]["input_path"])
    calibration_samples = read_jsonl(calibration_input)
    calibration_sample_ids = {sample.sample_id for sample in calibration_samples}
    calibration_template_groups = {sample.template_group for sample in calibration_samples}
    for split, path in sorted(test_inputs.items()):
        samples = read_jsonl(path)
        if not samples:
            raise ValueError(f"{split} input is empty")
        wrong_split = [sample.sample_id for sample in samples if sample.split != split]
        if wrong_split:
            raise ValueError(
                f"{split} input contains samples assigned to another split: {wrong_split[:5]}"
            )
        current_ids = {sample.sample_id for sample in samples}
        if calibration_sample_ids & current_ids:
            raise ValueError(
                f"calibration and final test inputs share sample IDs: "
                f"{sorted(calibration_sample_ids & current_ids)[:5]}"
            )
        if sample_ids & current_ids:
            raise ValueError(f"final test inputs share sample IDs across splits: {sorted(sample_ids & current_ids)[:5]}")
        sample_ids.update(current_ids)
        current_groups = {sample.template_group for sample in samples}
        if calibration_template_groups & current_groups:
            raise ValueError("calibration and final test inputs share template_group values")
        if template_groups & current_groups:
            raise ValueError("final test inputs share template_group values across splits")
        template_groups.update(current_groups)
    if recorded_paths != expected_paths:
        raise ValueError("authorization test_input_paths do not match the run")
    if recorded_hashes != expected_hashes:
        raise ValueError("authorization test_input_sha256 values do not match the run")
    return payload


def claim_final_test_ledger(
    ledger_path: str | Path,
    *,
    authorization_path: str | Path,
    registry_path: str | Path,
    model_dir: str | Path,
    calibration_path: str | Path,
    calibration_report_path: str | Path,
    policy_path: str | Path,
    test_inputs: dict[str, str | Path],
    attack_threshold: float,
    run_id: str,
    output_dir: str | Path,
) -> dict[str, Any]:
    """Atomically claim the one formal final-test matrix; an existing ledger is fatal."""

    if not isinstance(run_id, str) or not run_id.strip():
        raise ValueError("run_id must be non-empty")
    output_dir = Path(output_dir)
    if output_dir.exists():
        raise FileExistsError(f"refusing to overwrite final-test output directory: {output_dir}")
    authorization = validate_final_test_authorization(
        authorization_path,
        registry_path=registry_path,
        model_dir=model_dir,
        calibration_path=calibration_path,
        calibration_report_path=calibration_report_path,
        policy_path=policy_path,
        test_inputs=test_inputs,
        attack_threshold=attack_threshold,
    )
    calibration_payload = _read_object(calibration_path, description="calibration artifact")
    ledger_path = Path(ledger_path)
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "status": "claimed",
        "run_id": run_id,
        "claimed_at": datetime.now(timezone.utc).isoformat(),
        "protocol_version": authorization["protocol_version"],
        "protocol_registry_path": str(Path(registry_path).resolve()),
        "protocol_registry_sha256": sha256_file(registry_path),
        "test_splits": list(FINAL_TEST_SPLITS),
        "attack_threshold": attack_threshold,
        "authorization_path": str(Path(authorization_path).resolve()),
        "authorization_sha256": sha256_file(authorization_path),
        "model_dir": str(Path(model_dir).resolve()),
        "model_artifact_sha256": artifact_tree_sha256(model_dir),
        "model_revision": authorization.get("model_revision"),
        "calibration_path": str(Path(calibration_path).resolve()),
        "calibration_sha256": sha256_file(calibration_path),
        "calibration_version": calibration_payload.get("version"),
        "calibration_report_path": str(Path(calibration_report_path).resolve()),
        "calibration_report_sha256": sha256_file(calibration_report_path),
        "policy_path": str(Path(policy_path).resolve()),
        "policy_sha256": sha256_file(policy_path),
        "policy_version": load_policy_snapshot(policy_path)["version"],
        "test_input_paths": {
            split: str(Path(path).resolve()) for split, path in sorted(test_inputs.items())
        },
        "test_input_sha256": {
            split: sha256_file(path) for split, path in sorted(test_inputs.items())
        },
        "output_dir": str(output_dir.resolve()),
    }
    try:
        with ledger_path.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    except FileExistsError as exc:
        raise FileExistsError(
            f"final-test ledger already exists; refusing a second formal matrix: {ledger_path}"
        ) from exc
    return payload


def complete_final_test_ledger(
    ledger_path: str | Path, *, run_id: str, result_paths: dict[str, str | Path]
) -> dict[str, Any]:
    """Mark a claimed matrix complete only after all three result directories exist."""

    ledger_path = Path(ledger_path)
    payload = _read_object(ledger_path, description="final-test ledger")
    if payload.get("status") != "claimed" or payload.get("run_id") != run_id:
        raise ValueError("final-test ledger is not a matching claimed run")
    if set(result_paths) != set(FINAL_TEST_SPLITS):
        raise ValueError(f"result_paths must contain exactly {list(FINAL_TEST_SPLITS)}")
    output_value = payload.get("output_dir")
    if not isinstance(output_value, str) or not output_value.strip():
        raise ValueError("final-test ledger output_dir is invalid")
    output_root = Path(output_value)
    if not output_root.is_absolute():
        raise ValueError("final-test ledger output_dir must be absolute")
    try:
        calibration_path = Path(payload["calibration_path"])
        calibration_sha256 = payload["calibration_sha256"]
        calibration_payload = _read_object(
            calibration_path, description="claimed calibration artifact"
        )
        if sha256_file(calibration_path) != calibration_sha256:
            raise ValueError("calibration artifact changed after ledger claim")
        if calibration_payload.get("version") != "2" or calibration_payload.get(
            "version"
        ) != payload.get("calibration_version"):
            raise ValueError("claimed calibration artifact version is invalid")
        calibration_metadata = calibration_payload.get("metadata")
        if not isinstance(calibration_metadata, dict):
            raise ValueError("claimed calibration artifact metadata is missing")
        validate_frozen_calibration_metadata(calibration_metadata)
    except KeyError as exc:
        raise ValueError(f"final-test ledger is missing calibration binding: {exc.args[0]}") from exc
    for path_key, hash_key, description in (
        ("authorization_path", "authorization_sha256", "authorization"),
        ("calibration_report_path", "calibration_report_sha256", "calibration report"),
        ("policy_path", "policy_sha256", "policy"),
        ("protocol_registry_path", "protocol_registry_sha256", "protocol registry"),
    ):
        try:
            current_hash = sha256_file(payload[path_key])
            recorded_hash = payload[hash_key]
        except (KeyError, OSError, TypeError) as exc:
            raise ValueError(f"final-test ledger {description} binding is invalid") from exc
        if current_hash != recorded_hash:
            raise ValueError(f"{description} changed after ledger claim")
    if artifact_tree_sha256(payload["model_dir"]) != payload["model_artifact_sha256"]:
        raise ValueError("model artifact changed after ledger claim")
    expected_input_paths = payload.get("test_input_paths")
    expected_input_hashes = payload.get("test_input_sha256")
    if not isinstance(expected_input_paths, dict) or not isinstance(expected_input_hashes, dict):
        raise ValueError("final-test ledger test input bindings are missing")
    for split in FINAL_TEST_SPLITS:
        if split not in expected_input_paths or split not in expected_input_hashes:
            raise ValueError(f"final-test ledger is missing {split} input binding")
        if sha256_file(expected_input_paths[split]) != expected_input_hashes[split]:
            raise ValueError(f"{split} input changed after ledger claim")
    result_files: dict[str, dict[str, str]] = {}
    for split, path in sorted(result_paths.items()):
        result_dir = Path(path)
        if not result_dir.is_dir():
            raise FileNotFoundError(f"final-test result directory does not exist: {result_dir}")
        expected_result_dir = output_root / split
        if result_dir.resolve() != expected_result_dir.resolve():
            raise ValueError(f"{split} result directory does not match the claimed output_dir")
        prediction_path = result_dir / "predictions.jsonl"
        metrics_path = result_dir / "metrics.json"
        if not prediction_path.is_file() or not metrics_path.is_file():
            raise ValueError(f"{split} result must contain predictions.jsonl and metrics.json")
        rows = load_prediction_jsonl(prediction_path, expected_split=split)
        expected_samples = read_jsonl(expected_input_paths[split])
        expected_by_id = {sample.sample_id: sample for sample in expected_samples}
        if set(row["sample_id"] for row in rows) != set(expected_by_id):
            raise ValueError(f"{split} predictions do not cover exactly the claimed samples")
        for row in rows:
            sample = expected_by_id[row["sample_id"]]
            if row["template_group"] != sample.template_group or row["true_risk"] != sample.risk_label:
                raise ValueError(f"{split} prediction metadata does not match the claimed input")
            if row.get("calibrated") is not True:
                raise ValueError(f"{split} predictions must record calibrated=true")
            if row.get("calibration_version") != calibration_payload["version"]:
                raise ValueError(f"{split} prediction calibration version is not bound")
            if row.get("calibration_sha256") != calibration_sha256:
                raise ValueError(f"{split} prediction calibration hash is not bound")
            if row.get("revision") != payload.get("model_revision"):
                raise ValueError(f"{split} prediction model revision is not bound")
            if not math.isclose(
                float(row["attack_threshold"]),
                float(payload["attack_threshold"]),
                rel_tol=0.0,
                abs_tol=1e-15,
            ):
                raise ValueError(f"{split} prediction threshold does not match the ledger")
        metrics = _read_object(metrics_path, description=f"{split} metrics")
        if metrics.get("threshold_source") != "calibration_only":
            raise ValueError(f"{split} metrics threshold source is invalid")
        operating_point = metrics.get("operating_point")
        if not isinstance(operating_point, dict):
            raise ValueError(f"{split} metrics operating point is missing")
        try:
            metrics_threshold = float(operating_point["threshold"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"{split} metrics threshold is invalid") from exc
        if not math.isclose(
            metrics_threshold,
            float(payload["attack_threshold"]),
            rel_tol=0.0,
            abs_tol=1e-15,
        ):
            raise ValueError(f"{split} metrics threshold does not match the ledger")
        expected_metrics = evaluate_risk_predictions(
            [RISK_LABELS.index(row["true_risk"]) for row in rows],
            [[row["risk_probabilities"][label] for label in RISK_LABELS] for row in rows],
            attack_threshold=float(payload["attack_threshold"]),
        )
        if metrics != expected_metrics:
            raise ValueError(f"{split} metrics do not match predictions")
        files = [item for item in result_dir.rglob("*") if item.is_file()]
        result_files[split] = {
            item.relative_to(result_dir).as_posix(): sha256_file(item)
            for item in sorted(files, key=lambda value: value.relative_to(result_dir).as_posix())
        }
    payload["status"] = "completed"
    payload["completed_at"] = datetime.now(timezone.utc).isoformat()
    payload["result_files"] = result_files
    serialized = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            prefix=f".{ledger_path.name}.",
            suffix=".tmp",
            dir=ledger_path.parent,
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            handle.write(serialized)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, ledger_path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
    return payload
