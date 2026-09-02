from __future__ import annotations

import json
import math
import os
import re
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import yaml
from scipy.optimize import minimize_scalar
from sklearn.metrics import log_loss

from intentfence.constants import LEGACY_ALIGNMENT_LABELS, RISK_LABELS, TASK_ALIGNMENT_LABELS
from intentfence.metrics import softmax
from intentfence.run_manifest import artifact_tree_sha256, sha256_file
from intentfence.schema import read_jsonl

CALIBRATION_METADATA_VERSION = 3
CALIBRATION_AUTHORIZATION_VERSION = 1
CALIBRATION_BUNDLE_MARKER_VERSION = 1
CALIBRATION_ARRAY_NAMES = (
    "risk_logits",
    "alignment_logits",
    "risk_labels",
    "alignment_labels",
)


def calibration_bundle_marker_path(logits_path: str | Path) -> Path:
    """Return the commit marker path for an NPZ/sidecar calibration bundle."""

    return Path(logits_path).with_suffix(".complete")


def _require_sha256(value: Any, name: str) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ValueError(f"{name} must be a lowercase 64-character SHA-256")
    return value


def _require_absolute_path(value: Any, name: str) -> Path:
    if isinstance(value, Path):
        path = value
    elif isinstance(value, str) and value.strip():
        path = Path(value)
    else:
        raise ValueError(f"{name} must be a non-empty path")
    if not path.is_absolute():
        raise ValueError(f"{name} must be an absolute path")
    return path.resolve()


def _validate_owner_timestamp(payload: Mapping[str, Any], *, description: str) -> None:
    approved_at = payload.get("approved_at")
    if not isinstance(approved_at, str) or not re.search(
        r"(?:Z|[+-]\d{2}:\d{2})$", approved_at
    ):
        raise ValueError(f"{description} approved_at must include a timezone")
    try:
        parsed_timestamp = datetime.fromisoformat(approved_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{description} approved_at must be ISO-8601") from exc
    if parsed_timestamp.tzinfo is None:
        raise ValueError(f"{description} approved_at must include a timezone")


def load_policy_snapshot(policy_path: str | Path) -> dict[str, Any]:
    """Load and hash the exact runtime policy used by a calibration run."""

    source = Path(policy_path)
    if not source.is_file():
        raise FileNotFoundError(f"policy file does not exist: {source}")
    from intentfence.policy import PolicyEngine

    engine = PolicyEngine.from_yaml(source)
    config = engine.config
    return {
        "path": str(source.resolve()),
        "sha256": sha256_file(source),
        "version": config.version,
        "allow_max": config.allow_max,
        "block_min": config.block_min,
        "tool_weights": dict(sorted(config.tool_weights.items())),
        "sensitive_always_confirm": config.sensitive_always_confirm,
        "external_communication_minimum": config.external_communication_minimum,
        "fail_open_tool_types": list(config.fail_open_tool_types),
        "fail_closed_tool_types": list(config.fail_closed_tool_types),
    }


def load_calibration_protocol_snapshot(registry_path: str | Path) -> dict[str, Any]:
    """Load the frozen registry fields that control C2c calibration."""

    source = Path(registry_path)
    if not source.is_file():
        raise FileNotFoundError(f"protocol registry does not exist: {source}")
    try:
        payload = yaml.safe_load(source.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ValueError(f"protocol registry must be valid YAML: {source}") from exc
    if not isinstance(payload, dict) or payload.get("status") != "frozen":
        raise ValueError("calibration requires a frozen experiment registry")
    calibration = payload.get("calibration")
    if not isinstance(calibration, dict):
        raise ValueError("protocol registry calibration contract is missing")
    if not isinstance(payload.get("protocol_version"), str) or not payload[
        "protocol_version"
    ].strip():
        raise ValueError("protocol registry protocol_version is invalid")
    for field in ("split", "method", "threshold_source"):
        if not isinstance(calibration.get(field), str) or not calibration[field].strip():
            raise ValueError(f"protocol registry calibration {field} is invalid")
    if calibration["split"] != "calibration":
        raise ValueError("protocol registry calibration split must be calibration")
    if calibration["method"] != "temperature_scaling_per_head":
        raise ValueError("protocol registry calibration method is unsupported")
    if calibration["threshold_source"] != "calibration_only":
        raise ValueError("protocol registry calibration threshold source is invalid")
    try:
        benign_fpr_ceiling = float(calibration["benign_fpr_ceiling"])
        minimum_viable_attack_tpr = float(calibration["minimum_viable_attack_tpr"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("protocol registry calibration thresholds are invalid") from exc
    if not math.isfinite(benign_fpr_ceiling) or not 0 <= benign_fpr_ceiling < 1:
        raise ValueError("protocol registry benign_fpr_ceiling must be finite in [0, 1)")
    if not math.isfinite(minimum_viable_attack_tpr) or not 0 <= minimum_viable_attack_tpr <= 1:
        raise ValueError(
            "protocol registry minimum_viable_attack_tpr must be finite in [0, 1]"
        )
    return {
        "path": str(source.resolve()),
        "sha256": sha256_file(source),
        "protocol_version": payload["protocol_version"],
        "split": calibration["split"],
        "method": calibration["method"],
        "threshold_source": calibration["threshold_source"],
        "benign_fpr_ceiling": benign_fpr_ceiling,
        "minimum_viable_attack_tpr": minimum_viable_attack_tpr,
    }


def _integer_labels(value: Any, *, name: str, class_count: int) -> np.ndarray:
    raw = np.asarray(value)
    if raw.ndim != 1:
        raise ValueError(f"{name} must be one-dimensional")
    try:
        numeric = np.asarray(raw, dtype=float)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must contain integer class ids") from exc
    if (
        not np.isfinite(numeric).all()
        or not np.equal(numeric, np.floor(numeric)).all()
    ):
        raise ValueError(f"{name} must contain integer class ids")
    labels = numeric.astype(int)
    if np.any(labels < 0) or np.any(labels >= class_count):
        raise ValueError(f"{name} contains a class id outside [0, {class_count})")
    return labels


def validate_calibration_arrays(arrays: Mapping[str, Any]) -> dict[str, int]:
    """Validate the frozen-model logits contract before any calibration fit."""

    missing = [name for name in CALIBRATION_ARRAY_NAMES if name not in arrays]
    if missing:
        raise ValueError(f"calibration logits are missing arrays: {missing}")
    risk_logits = np.asarray(arrays["risk_logits"], dtype=float)
    alignment_logits = np.asarray(arrays["alignment_logits"], dtype=float)
    if (
        risk_logits.ndim != 2
        or risk_logits.shape[0] == 0
        or risk_logits.shape[1] != len(RISK_LABELS)
    ):
        raise ValueError(f"risk_logits must have shape [samples, {len(RISK_LABELS)}]")
    if (
        alignment_logits.ndim != 2
        or alignment_logits.shape[0] != risk_logits.shape[0]
        or alignment_logits.shape[1] not in (2, len(TASK_ALIGNMENT_LABELS))
    ):
        raise ValueError(
            "alignment_logits must have shape [samples, 2] or "
            f"[samples, {len(TASK_ALIGNMENT_LABELS)}]"
        )
    if not np.isfinite(risk_logits).all() or not np.isfinite(alignment_logits).all():
        raise ValueError("calibration logits must contain only finite values")
    risk_labels = _integer_labels(
        arrays["risk_labels"], name="risk_labels", class_count=len(RISK_LABELS)
    )
    alignment_labels = _integer_labels(
        arrays["alignment_labels"],
        name="alignment_labels",
        class_count=alignment_logits.shape[1],
    )
    if len(risk_labels) != len(risk_logits) or len(alignment_labels) != len(risk_logits):
        raise ValueError("logit and label arrays must contain the same number of samples")
    if len(np.unique(risk_labels)) < 2:
        raise ValueError("risk_labels must contain at least two classes for calibration")
    if not np.any(risk_labels == 0) or not np.any(risk_labels != 0):
        raise ValueError("risk_labels must contain benign and attack samples for FPR calibration")
    if len(np.unique(alignment_labels)) < 2:
        raise ValueError("alignment_labels must contain at least two classes for calibration")
    return {
        "samples": int(len(risk_labels)),
        "risk_classes": int(risk_logits.shape[1]),
        "alignment_classes": int(alignment_logits.shape[1]),
    }


def load_calibration_arrays(
    logits_path: str | Path, metadata_path: str | Path | None = None
) -> tuple[dict[str, np.ndarray], dict[str, Any]]:
    """Load logits and require a matching, hash-verified calibration sidecar."""

    logits_path = Path(logits_path)
    if not logits_path.is_file():
        raise FileNotFoundError(f"calibration logits do not exist: {logits_path}")
    metadata_path = Path(metadata_path) if metadata_path is not None else logits_path.with_suffix(".json")
    if not metadata_path.is_file():
        raise FileNotFoundError(f"calibration metadata does not exist: {metadata_path}")
    marker_path = calibration_bundle_marker_path(logits_path)
    if not marker_path.is_file():
        raise FileNotFoundError(f"calibration bundle commit marker does not exist: {marker_path}")
    try:
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid calibration bundle commit marker: {marker_path}") from exc
    if not isinstance(marker, dict) or marker.get("format_version") != CALIBRATION_BUNDLE_MARKER_VERSION:
        raise ValueError("calibration bundle commit marker format is invalid")
    if marker.get("logits_path") != str(logits_path.resolve()):
        raise ValueError("calibration bundle commit marker logits path does not match")
    if marker.get("metadata_path") != str(metadata_path.resolve()):
        raise ValueError("calibration bundle commit marker metadata path does not match")
    if marker.get("logits_sha256") != sha256_file(logits_path):
        raise ValueError("calibration bundle commit marker logits hash does not match")
    if marker.get("metadata_sha256") != sha256_file(metadata_path):
        raise ValueError("calibration bundle commit marker metadata hash does not match")
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid calibration metadata JSON: {metadata_path}") from exc
    if not isinstance(metadata, dict):
        raise ValueError("calibration metadata must be a JSON object")
    if metadata.get("format_version") != CALIBRATION_METADATA_VERSION:
        raise ValueError(
            "calibration metadata format_version must be "
            f"{CALIBRATION_METADATA_VERSION}"
        )
    if metadata.get("split") != "calibration":
        raise ValueError("calibration logits must be exported from split='calibration'")
    input_value = metadata.get("input")
    input_sha256 = metadata.get("input_sha256")
    input_path = _require_absolute_path(input_value, "calibration metadata input")
    _require_sha256(input_sha256, "calibration metadata input_sha256")
    if not input_path.is_file():
        raise FileNotFoundError(f"calibration input from metadata does not exist: {input_path}")
    if sha256_file(input_path) != input_sha256:
        raise ValueError("calibration input hash does not match metadata")
    metadata_model_dir = _require_absolute_path(
        metadata.get("model_dir"), "calibration metadata model_dir"
    )
    if not metadata_model_dir.is_dir():
        raise FileNotFoundError(
            f"calibration model artifact directory from metadata does not exist: {metadata_model_dir}"
        )
    model_artifact_sha256 = _require_sha256(
        metadata.get("model_artifact_sha256"),
        "calibration metadata model_artifact_sha256",
    )
    if artifact_tree_sha256(metadata_model_dir) != model_artifact_sha256:
        raise ValueError("calibration model artifact hash does not match metadata")
    model_revision = metadata.get("model_revision")
    if not isinstance(model_revision, str) or not model_revision.strip():
        raise ValueError("calibration metadata must include model_revision")
    logits_sha256 = _require_sha256(
        metadata.get("logits_sha256"), "calibration metadata logits_sha256"
    )
    if sha256_file(logits_path) != logits_sha256:
        raise ValueError("calibration logits hash does not match metadata")
    with np.load(logits_path, allow_pickle=False) as loaded:
        arrays = {name: np.asarray(loaded[name]).copy() for name in CALIBRATION_ARRAY_NAMES if name in loaded}
    summary = validate_calibration_arrays(arrays)
    if metadata.get("samples") != summary["samples"]:
        raise ValueError("calibration metadata sample count does not match logits")
    try:
        input_samples = read_jsonl(input_path)
    except (OSError, ValueError) as exc:
        raise ValueError(f"calibration input is not valid canonical JSONL: {input_path}") from exc
    if len(input_samples) != summary["samples"]:
        raise ValueError("calibration input row count does not match logits")
    sample_ids = metadata.get("sample_ids")
    if (
        not isinstance(sample_ids, list)
        or len(sample_ids) != summary["samples"]
        or any(not isinstance(value, str) or not value.strip() for value in sample_ids)
        or len(set(sample_ids)) != len(sample_ids)
    ):
        raise ValueError("calibration metadata sample_ids must be an ordered unique list")
    actual_sample_ids = [sample.sample_id for sample in input_samples]
    if sample_ids != actual_sample_ids:
        raise ValueError("calibration metadata sample_ids do not match the input")
    template_groups = metadata.get("template_groups")
    if (
        not isinstance(template_groups, list)
        or len(template_groups) != summary["samples"]
        or any(not isinstance(value, str) or not value.strip() for value in template_groups)
    ):
        raise ValueError("calibration metadata template_groups must match the input")
    if template_groups != [sample.template_group for sample in input_samples]:
        raise ValueError("calibration metadata template_groups do not match the input")
    expected_risk_labels = np.asarray(
        [RISK_LABELS.index(sample.risk_label) for sample in input_samples], dtype=int
    )
    if not np.array_equal(np.asarray(arrays["risk_labels"], dtype=int), expected_risk_labels):
        raise ValueError("calibration risk_labels do not match the canonical input")
    alignment_target = metadata.get("alignment_target", "legacy_binary")
    if alignment_target == "task_alignment":
        if any(sample.task_alignment_label is None for sample in input_samples):
            raise ValueError("task-alignment calibration input labels are incomplete")
        expected_alignment_labels = np.asarray(
            [TASK_ALIGNMENT_LABELS.index(sample.task_alignment_label) for sample in input_samples],
            dtype=int,
        )
    elif alignment_target == "legacy_binary":
        expected_alignment_labels = np.asarray(
            [sample.alignment_label for sample in input_samples], dtype=int
        )
    else:
        raise ValueError("calibration metadata alignment_target is invalid")
    if not np.array_equal(
        np.asarray(arrays["alignment_labels"], dtype=int), expected_alignment_labels
    ):
        raise ValueError("calibration alignment_labels do not match the canonical input")
    expected_shapes = {
        "risk_logits": [summary["samples"], summary["risk_classes"]],
        "alignment_logits": [summary["samples"], summary["alignment_classes"]],
    }
    for name, shape in expected_shapes.items():
        recorded = metadata.get(f"{name}_shape")
        if recorded is not None and recorded != shape:
            raise ValueError(f"calibration metadata shape for {name} does not match logits")
    if metadata.get("risk_labels") != list(RISK_LABELS):
        raise ValueError("calibration metadata risk_labels do not match the frozen label contract")
    expected_alignment_labels = list(
        TASK_ALIGNMENT_LABELS if summary["alignment_classes"] == 4 else LEGACY_ALIGNMENT_LABELS
    )
    if metadata.get("alignment_labels") != expected_alignment_labels:
        raise ValueError(
            "calibration metadata alignment_labels do not match the logits class count"
        )
    return arrays, metadata


def validate_calibration_authorization(
    authorization_path: str | Path,
    *,
    logits_path: str | Path,
    metadata: Mapping[str, Any],
    metadata_path: str | Path,
    policy_snapshot: Mapping[str, Any],
    protocol_snapshot: Mapping[str, Any],
    target_fpr: float,
) -> dict[str, Any]:
    """Require owner authorization tied to every C2c calibration input."""

    authorization_path = Path(authorization_path)
    if not authorization_path.is_file():
        raise FileNotFoundError(f"calibration authorization does not exist: {authorization_path}")
    try:
        payload = json.loads(authorization_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("calibration authorization must be valid JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("calibration authorization must be a JSON object")
    if payload.get("schema_version") != CALIBRATION_AUTHORIZATION_VERSION:
        raise ValueError(
            "calibration authorization schema_version must be "
            f"{CALIBRATION_AUTHORIZATION_VERSION}"
        )
    if payload.get("calibration_authorized") is not True:
        raise ValueError("calibration authorization requires calibration_authorized=true")
    if payload.get("human_verified") is not True:
        raise ValueError("calibration authorization requires independent human_verified=true")
    if payload.get("final_test_lock_preserved") is not True:
        raise ValueError("calibration authorization must preserve the final-test lock")
    if not isinstance(payload.get("approved_by_project_owner"), str) or not payload[
        "approved_by_project_owner"
    ].strip():
        raise ValueError("calibration authorization requires approved_by_project_owner")
    _validate_owner_timestamp(payload, description="calibration authorization")

    if not np.isfinite(target_fpr) or not 0 <= target_fpr < 1:
        raise ValueError("target_fpr must be finite and in [0, 1)")
    if payload.get("target_fpr") != target_fpr:
        raise ValueError("calibration authorization target_fpr does not match the run")
    if payload.get("protocol_registry_path") != protocol_snapshot.get("path"):
        raise ValueError("calibration authorization protocol registry path does not match the run")
    if payload.get("protocol_registry_sha256") != protocol_snapshot.get("sha256"):
        raise ValueError("calibration authorization protocol registry hash does not match the run")
    if payload.get("protocol_version") != protocol_snapshot.get("protocol_version"):
        raise ValueError("calibration authorization protocol version does not match the run")
    if payload.get("minimum_viable_attack_tpr") != protocol_snapshot.get(
        "minimum_viable_attack_tpr"
    ):
        raise ValueError("calibration authorization minimum viable TPR does not match the run")

    expected_logits_sha256 = sha256_file(logits_path)
    if payload.get("logits_sha256") != expected_logits_sha256:
        raise ValueError("calibration authorization logits_sha256 does not match the NPZ")
    expected_metadata_path = _require_absolute_path(
        metadata_path, "calibration metadata path"
    )
    if payload.get("metadata_path") != str(expected_metadata_path):
        raise ValueError("calibration authorization metadata_path does not match the sidecar")
    if payload.get("metadata_sha256") != sha256_file(expected_metadata_path):
        raise ValueError("calibration authorization metadata_sha256 does not match the sidecar")
    if payload.get("input_sha256") != metadata.get("input_sha256"):
        raise ValueError("calibration authorization input_sha256 does not match metadata")
    if payload.get("input") != metadata.get("input"):
        raise ValueError("calibration authorization input does not match metadata")
    if payload.get("model_dir") != metadata.get("model_dir"):
        raise ValueError("calibration authorization model_dir does not match metadata")
    if payload.get("model_artifact_sha256") != metadata.get("model_artifact_sha256"):
        raise ValueError(
            "calibration authorization model_artifact_sha256 does not match metadata"
        )
    if payload.get("model_revision") != metadata.get("model_revision"):
        raise ValueError("calibration authorization model_revision does not match metadata")
    policy_path = _require_absolute_path(
        policy_snapshot.get("path"), "policy snapshot path"
    )
    if payload.get("policy_path") != str(policy_path):
        raise ValueError("calibration authorization policy_path does not match the run")
    if payload.get("policy_sha256") != policy_snapshot.get("sha256"):
        raise ValueError("calibration authorization policy_sha256 does not match the run")
    if payload.get("policy_version") != policy_snapshot.get("version"):
        raise ValueError("calibration authorization policy_version does not match the run")
    return payload


def validate_calibration_export_authorization(
    authorization_path: str | Path,
    *,
    model_dir: str | Path,
    model_artifact_sha256: str,
    model_revision: str,
    input_path: str | Path,
    input_sha256: str,
) -> dict[str, Any]:
    """Require owner authorization before exporting real calibration logits."""

    authorization_path = Path(authorization_path)
    if not authorization_path.is_file():
        raise FileNotFoundError(
            f"calibration export authorization does not exist: {authorization_path}"
        )
    try:
        payload = json.loads(authorization_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("calibration export authorization must be valid JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("calibration export authorization must be a JSON object")
    if payload.get("schema_version") != CALIBRATION_AUTHORIZATION_VERSION:
        raise ValueError(
            "calibration export authorization schema_version must be "
            f"{CALIBRATION_AUTHORIZATION_VERSION}"
        )
    if payload.get("calibration_export_authorized") is not True:
        raise ValueError(
            "calibration export authorization requires calibration_export_authorized=true"
        )
    if payload.get("human_verified") is not True:
        raise ValueError("calibration export authorization requires independent human_verified=true")
    if payload.get("final_test_lock_preserved") is not True:
        raise ValueError("calibration export authorization must preserve the final-test lock")
    if not isinstance(payload.get("approved_by_project_owner"), str) or not payload[
        "approved_by_project_owner"
    ].strip():
        raise ValueError("calibration export authorization requires approved_by_project_owner")
    _validate_owner_timestamp(payload, description="calibration export authorization")

    expected_model_dir = _require_absolute_path(model_dir, "model_dir")
    if payload.get("model_dir") != str(expected_model_dir):
        raise ValueError("calibration export authorization model_dir does not match the run")
    expected_model_artifact_sha256 = _require_sha256(
        model_artifact_sha256, "model_artifact_sha256"
    )
    if payload.get("model_artifact_sha256") != expected_model_artifact_sha256:
        raise ValueError(
            "calibration export authorization model_artifact_sha256 does not match the run"
        )
    if not isinstance(model_revision, str) or not model_revision.strip():
        raise ValueError("model_revision must be a non-empty string")
    if payload.get("model_revision") != model_revision:
        raise ValueError(
            "calibration export authorization model_revision does not match the run"
        )
    expected_input_path = _require_absolute_path(input_path, "input_path")
    if payload.get("input") != str(expected_input_path):
        raise ValueError("calibration export authorization input does not match the run")
    expected_input_sha256 = _require_sha256(input_sha256, "input_sha256")
    if payload.get("input_sha256") != expected_input_sha256:
        raise ValueError(
            "calibration export authorization input_sha256 does not match the run"
        )
    return payload


def validate_frozen_calibration_metadata(
    metadata: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate the self-contained metadata required by a frozen calibration artifact."""

    if not isinstance(metadata, Mapping):
        raise ValueError("calibration metadata must be a JSON object")
    if metadata.get("format_version") != 1:
        raise ValueError("calibration metadata format_version must be 1")
    if metadata.get("status") != "frozen":
        raise ValueError("calibration artifact must have status=frozen")
    if metadata.get("claim_scope") != "calibration_split_only_not_final_test_result":
        raise ValueError("calibration artifact claim scope is invalid")
    if metadata.get("threshold_source") != "calibration_only":
        raise ValueError("calibration artifact threshold source is invalid")
    try:
        frozen_threshold = float(metadata.get("frozen_attack_threshold"))
    except (TypeError, ValueError) as exc:
        raise ValueError("calibration artifact frozen_attack_threshold is invalid") from exc
    if not math.isfinite(frozen_threshold) or not 0 <= frozen_threshold <= 1:
        raise ValueError("calibration artifact frozen_attack_threshold must be finite in [0, 1]")

    provenance = metadata.get("provenance")
    if not isinstance(provenance, Mapping):
        raise ValueError("calibration artifact provenance is missing")
    for field in (
        "logits_path",
        "metadata_path",
        "input_path",
        "model_dir",
        "policy_path",
        "authorization_path",
        "protocol_registry_path",
    ):
        _require_absolute_path(provenance.get(field), f"calibration provenance {field}")
    for field in (
        "logits_sha256",
        "metadata_sha256",
        "input_sha256",
        "model_artifact_sha256",
        "policy_sha256",
        "authorization_sha256",
        "protocol_registry_sha256",
    ):
        _require_sha256(provenance.get(field), f"calibration provenance {field}")
    for field in (
        "split",
        "model_revision",
        "policy_version",
        "protocol_version",
        "approved_by_project_owner",
    ):
        value = provenance.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"calibration provenance {field} must be a non-empty string")
    if provenance.get("split") != "calibration":
        raise ValueError("calibration provenance split must be calibration")
    protocol = metadata.get("protocol")
    if not isinstance(protocol, Mapping):
        raise ValueError("calibration artifact protocol snapshot is missing")
    protocol_path = _require_absolute_path(
        protocol.get("path"), "calibration protocol registry path"
    )
    protocol_sha256 = _require_sha256(
        protocol.get("sha256"), "calibration protocol registry sha256"
    )
    protocol_version = protocol.get("protocol_version")
    if not isinstance(protocol_version, str) or not protocol_version.strip():
        raise ValueError("calibration protocol version must be a non-empty string")
    if provenance.get("protocol_registry_path") != str(protocol_path):
        raise ValueError("calibration protocol registry path does not match provenance")
    if provenance.get("protocol_registry_sha256") != protocol_sha256:
        raise ValueError("calibration protocol registry hash does not match provenance")
    if provenance.get("protocol_version") != protocol_version:
        raise ValueError("calibration protocol version does not match provenance")
    raw_samples = provenance.get("samples")
    if isinstance(raw_samples, bool) or not isinstance(raw_samples, int):
        raise ValueError("calibration provenance samples must be a positive integer")
    samples = raw_samples
    if samples <= 0:
        raise ValueError("calibration provenance samples must be a positive integer")

    policy = metadata.get("policy")
    if not isinstance(policy, Mapping):
        raise ValueError("calibration artifact policy snapshot is missing")
    policy_path = _require_absolute_path(policy.get("path"), "calibration policy path")
    policy_sha256 = _require_sha256(policy.get("sha256"), "calibration policy sha256")
    policy_version = policy.get("version")
    if not isinstance(policy_version, str) or not policy_version.strip():
        raise ValueError("calibration policy version must be a non-empty string")
    if provenance.get("policy_path") != str(policy_path):
        raise ValueError("calibration policy path does not match provenance")
    if provenance.get("policy_sha256") != policy_sha256:
        raise ValueError("calibration policy hash does not match provenance")
    if provenance.get("policy_version") != policy_version:
        raise ValueError("calibration policy version does not match provenance")

    parameters = metadata.get("parameters")
    if not isinstance(parameters, Mapping):
        raise ValueError("calibration artifact parameters are missing")
    try:
        target_fpr = float(parameters.get("target_fpr"))
    except (TypeError, ValueError) as exc:
        raise ValueError("calibration artifact target_fpr is invalid") from exc
    if not math.isfinite(target_fpr) or not 0 <= target_fpr < 1:
        raise ValueError("calibration artifact target_fpr must be finite in [0, 1)")
    quality_gates = metadata.get("quality_gates")
    if quality_gates != {"status": "passed"}:
        raise ValueError("calibration artifact quality gates are not passed")
    labels = metadata.get("labels")
    if not isinstance(labels, Mapping):
        raise ValueError("calibration artifact labels are missing")
    if labels.get("risk") != list(RISK_LABELS):
        raise ValueError("calibration artifact risk labels do not match the frozen contract")
    if labels.get("alignment") not in (
        list(LEGACY_ALIGNMENT_LABELS),
        list(TASK_ALIGNMENT_LABELS),
    ):
        raise ValueError("calibration artifact alignment labels do not match the frozen contract")
    return dict(metadata)


@dataclass
class TemperatureScaler:
    temperature: float = 1.0

    def __post_init__(self) -> None:
        if not np.isfinite(self.temperature) or self.temperature <= 0:
            raise ValueError("temperature must be positive and finite")

    def fit(self, logits: np.ndarray, labels: np.ndarray) -> TemperatureScaler:
        logits = np.asarray(logits, dtype=float)
        if logits.ndim != 2 or logits.shape[0] == 0:
            raise ValueError("logits must be a non-empty [samples, classes] array")
        if not np.isfinite(logits).all():
            raise ValueError("logits must contain only finite values")
        labels = _integer_labels(labels, name="labels", class_count=logits.shape[1])
        if logits.shape[0] != labels.shape[0]:
            raise ValueError("logits must be [samples, classes] and match labels")
        if logits.shape[0] < 2:
            raise ValueError("At least two calibration samples are required")
        if len(np.unique(labels)) < 2:
            raise ValueError("At least two label classes are required for calibration")

        def objective(log_temperature: float) -> float:
            temperature = float(np.exp(log_temperature))
            probabilities = softmax(logits / temperature)
            return float(log_loss(labels, probabilities, labels=list(range(logits.shape[1]))))

        result = minimize_scalar(objective, bounds=(-4.0, 4.0), method="bounded")
        if not result.success:
            raise RuntimeError(f"Temperature optimization failed: {result.message}")
        self.temperature = float(np.exp(result.x))
        return self

    def transform_logits(self, logits: np.ndarray) -> np.ndarray:
        if self.temperature <= 0:
            raise ValueError("temperature must be positive")
        logits = np.asarray(logits, dtype=float)
        if logits.ndim != 2 or logits.shape[0] == 0 or not np.isfinite(logits).all():
            raise ValueError("logits must be a non-empty finite [samples, classes] array")
        return logits / self.temperature

    def predict_proba(self, logits: np.ndarray) -> np.ndarray:
        return softmax(self.transform_logits(logits))

    def to_dict(self) -> dict[str, float]:
        return {"temperature": self.temperature}

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> TemperatureScaler:
        return cls(temperature=float(payload["temperature"]))


@dataclass
class MultiHeadCalibration:
    risk: TemperatureScaler
    alignment: TemperatureScaler
    version: str = "1"
    metadata: dict[str, Any] | None = None

    def save(self, path: str | Path, *, metadata: Mapping[str, Any] | None = None) -> None:
        output = Path(path)
        if output.exists():
            raise FileExistsError(f"refusing to overwrite calibration file: {output}")
        output.parent.mkdir(parents=True, exist_ok=True)
        bound_metadata = metadata if metadata is not None else self.metadata
        if bound_metadata is not None and not isinstance(bound_metadata, Mapping):
            raise ValueError("calibration metadata must be a mapping")
        if bound_metadata is not None:
            validate_frozen_calibration_metadata(bound_metadata)
        payload = {
            "version": self.version,
            "risk": self.risk.to_dict(),
            "alignment": self.alignment.to_dict(),
        }
        if bound_metadata is not None:
            payload["metadata"] = dict(bound_metadata)
        serialized = json.dumps(payload, indent=2, sort_keys=True) + "\n"
        with tempfile.TemporaryDirectory(
            prefix=".intentfence-calibration-", dir=output.parent
        ) as temporary_directory:
            staged = Path(temporary_directory) / output.name
            staged.write_text(serialized, encoding="utf-8")
            os.link(staged, output)
            staged.unlink()

    @classmethod
    def load(cls, path: str | Path) -> MultiHeadCalibration:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("calibration file must contain a JSON object")
        metadata = payload.get("metadata")
        if not isinstance(metadata, dict):
            raise ValueError("calibration file must include frozen metadata")
        validate_frozen_calibration_metadata(metadata)
        return cls(
            risk=TemperatureScaler.from_dict(payload["risk"]),
            alignment=TemperatureScaler.from_dict(payload["alignment"]),
            version=str(payload.get("version", "1")),
            metadata=metadata,
        )
